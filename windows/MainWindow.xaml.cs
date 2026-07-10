using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Data;
using System.Windows.Input;
using ProxmoxSpiceManager.Models;
using ProxmoxSpiceManager.Services;

namespace ProxmoxSpiceManager;

public partial class MainWindow : Window
{
    private AppConfig _config;
    private int _selectedClusterIdx = -1;
    private readonly Dictionary<string, (bool? Online, int? VmCount)> _clusterStatus = new();
    private readonly Dictionary<string, AuthInfo> _authCache = new();
    private ObservableCollection<VmDisplayItem> _vmItems = [];
    private ICollectionView? _vmView;
    private readonly Dictionary<string, string> _activeFilters = new();

    // Exposed for XAML binding
    public List<string> NoteOptionsList => _config.NoteOptions ?? [];

    public MainWindow()
    {
        InitializeComponent();
        _config = ConfigService.Load();
        _config.NoteOptions ??= [];
        _config.VmNotes ??= new Dictionary<string, string>();
        ConfigService.MigrateSecrets(_config);

        ThemeCombo.ItemsSource = Themes.All.Keys.ToList();
        ThemeCombo.SelectedItem = _config.Theme;

        VmGrid.ItemsSource = _vmItems;
        _vmView = CollectionViewSource.GetDefaultView(_vmItems);
        _vmView.Filter = VmFilterPredicate;

        // Right-click on column headers — use Preview (tunneling) so it fires before DataGrid swallows it
        VmGrid.PreviewMouseRightButtonUp += OnColumnHeaderRightClick;

        RefreshClusterList();

        if (_config.Clusters.Count > 0)
        {
            _selectedClusterIdx = 0;
            RefreshClusterList();
            Loaded += async (_, _) => await RefreshVmsAsync();
        }
    }

    private void SaveConfig()
    {
        _config.Version = "2.2.3";
        ConfigService.Save(_config);
    }

    // ── Theme ──────────────────────────────────────────────────────────────
    private void OnThemeChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ThemeCombo.SelectedItem is not string themeName) return;
        _config.Theme = themeName;
        ThemeManager.Apply(themeName);
        SaveConfig();
        RefreshClusterList();
    }

    // ── Cluster List ───────────────────────────────────────────────────────
    private void RefreshClusterList()
    {
        var items = new List<ClusterListItem>();
        for (int i = 0; i < _config.Clusters.Count; i++)
        {
            var c = _config.Clusters[i];
            _clusterStatus.TryGetValue(c.Name, out var status);
            items.Add(new ClusterListItem
            {
                Name = c.Name,
                Index = i,
                IsSelected = i == _selectedClusterIdx,
                Online = status.Online,
                VmCount = status.VmCount,
            });
        }
        ClusterList.ItemsSource = items;
    }

    private void OnClusterClick(object sender, MouseButtonEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.DataContext is ClusterListItem item)
        {
            _selectedClusterIdx = item.Index;
            RefreshClusterList();
            _ = RefreshVmsAsync();
        }
    }

    private void OnAddCluster(object sender, RoutedEventArgs e)
    {
        var dlg = new Dialogs.ClusterDialog(_config) { Owner = this };
        if (dlg.ShowDialog() == true && dlg.Result != null)
        {
            _config.Clusters.Add(dlg.Result);
            if (dlg.PendingSecret != null)
                ConfigService.SaveSecret(dlg.Result, dlg.PendingSecret);
            SaveConfig();
            _selectedClusterIdx = _config.Clusters.Count - 1;
            RefreshClusterList();
            _ = RefreshVmsAsync();
        }
    }

    private void OnEditCluster(object sender, RoutedEventArgs e)
    {
        if (_selectedClusterIdx < 0 || _selectedClusterIdx >= _config.Clusters.Count) return;
        var cluster = _config.Clusters[_selectedClusterIdx];
        var dlg = new Dialogs.ClusterDialog(_config, cluster) { Owner = this };
        if (dlg.ShowDialog() == true && dlg.Result != null)
        {
            _config.Clusters[_selectedClusterIdx] = dlg.Result;
            if (dlg.PendingSecret != null)
                ConfigService.SaveSecret(dlg.Result, dlg.PendingSecret);
            SaveConfig();
            _authCache.Remove(cluster.Name);
            RefreshClusterList();
            _ = RefreshVmsAsync();
        }
    }

    private void OnRemoveCluster(object sender, RoutedEventArgs e)
    {
        if (_selectedClusterIdx < 0 || _selectedClusterIdx >= _config.Clusters.Count) return;
        var cluster = _config.Clusters[_selectedClusterIdx];
        if (MessageBox.Show($"Remove cluster '{cluster.Name}'?", "Confirm",
            MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
            return;

        _authCache.Remove(cluster.Name);
        _clusterStatus.Remove(cluster.Name);
        _config.Clusters.RemoveAt(_selectedClusterIdx);
        SaveConfig();

        _selectedClusterIdx = Math.Min(_selectedClusterIdx, _config.Clusters.Count - 1);
        _vmItems.Clear();
        RefreshClusterList();
    }

    // ── Auth ───────────────────────────────────────────────────────────────
    private async Task<AuthInfo?> GetAuthAsync(ClusterConfig cluster)
    {
        if (_authCache.TryGetValue(cluster.Name, out var cached))
            return cached;

        if (cluster.AuthMethod == "token")
        {
            var secret = ConfigService.GetSecret(cluster);
            if (secret == null)
            {
                StatusLabel.Text = "Token secret not found — re-edit the cluster.";
                return null;
            }
            var auth = new AuthInfo
            {
                TokenId = cluster.TokenId,
                TokenSecret = secret,
                SkipTlsVerify = cluster.SkipTlsVerify,
            };
            _authCache[cluster.Name] = auth;
            return auth;
        }

        // Password auth — prompt
        var pwDlg = new Dialogs.PasswordDialog(cluster.Username, cluster.Host) { Owner = this };
        if (pwDlg.ShowDialog() != true || pwDlg.Password == null)
            return null;

        var authResult = await ProxmoxApi.AuthenticatePasswordAsync(
            cluster.Host, cluster.Username, pwDlg.Password, cluster.SkipTlsVerify);

        if (authResult == null)
        {
            StatusLabel.Text = "Authentication failed.";
            return null;
        }
        _authCache[cluster.Name] = authResult;
        return authResult;
    }

    // ── VM Refresh ─────────────────────────────────────────────────────────
    private async Task RefreshVmsAsync()
    {
        if (_selectedClusterIdx < 0 || _selectedClusterIdx >= _config.Clusters.Count)
            return;

        var cluster = _config.Clusters[_selectedClusterIdx];
        StatusLabel.Text = $"Loading VMs from {cluster.Name}...";

        var auth = await GetAuthAsync(cluster);
        if (auth == null)
        {
            _clusterStatus[cluster.Name] = (false, null);
            RefreshClusterList();
            return;
        }

        // Fetch pool memberships and node list in parallel
        var resourcesTask = ProxmoxApi.RequestAsync(
            cluster.Host, "/api2/json/cluster/resources?type=vm", auth: auth);
        var nodesTask = ProxmoxApi.RequestAsync(
            cluster.Host, "/api2/json/nodes", auth: auth);
        await Task.WhenAll(resourcesTask, nodesTask);

        var poolMap = new Dictionary<int, string>();
        var resourcesJson = await resourcesTask;
        if (resourcesJson?.TryGetProperty("data", out var resData) == true)
        {
            foreach (var res in resData.EnumerateArray())
            {
                if (res.TryGetProperty("vmid", out var rvmid) &&
                    res.TryGetProperty("pool", out var rpool) &&
                    rpool.GetString() is string poolName && poolName.Length > 0)
                {
                    poolMap[rvmid.GetInt32()] = poolName;
                }
            }
        }

        var nodesJson = await nodesTask;
        if (nodesJson == null || !nodesJson.Value.TryGetProperty("data", out var nodesData))
        {
            StatusLabel.Text = $"Failed to connect to {cluster.Name}";
            _clusterStatus[cluster.Name] = (false, null);
            RefreshClusterList();
            return;
        }

        // Fetch per-node VM lists in parallel
        var nodeNames = nodesData.EnumerateArray()
            .Select(n => n.GetProperty("node").GetString() ?? "")
            .Where(n => n.Length > 0)
            .ToList();

        var nodeVmTasks = nodeNames.Select(nodeName =>
            ProxmoxApi.RequestAsync(cluster.Host, $"/api2/json/nodes/{nodeName}/qemu", auth: auth)
        ).ToList();
        var nodeVmResults = await Task.WhenAll(nodeVmTasks);

        // Collect all VMs with their node names, then fetch config+snapshot in parallel
        var vmEntries = new List<(int vmid, string name, string status, string nodeName, string pool)>();
        for (int i = 0; i < nodeNames.Count; i++)
        {
            var vmJson = nodeVmResults[i];
            if (vmJson == null || !vmJson.Value.TryGetProperty("data", out var vmData))
                continue;

            foreach (var vm in vmData.EnumerateArray())
            {
                var vmid = vm.GetProperty("vmid").GetInt32();
                var name = vm.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "";
                var status = vm.TryGetProperty("status", out var s) ? s.GetString() ?? "" : "";
                var pool = poolMap.GetValueOrDefault(vmid, "");
                vmEntries.Add((vmid, name, status, nodeNames[i], pool));
            }
        }

        // Fetch config for all VMs in parallel to check for SPICE display
        var configTasks = vmEntries.Select(e =>
            ProxmoxApi.RequestAsync(cluster.Host,
                $"/api2/json/nodes/{e.nodeName}/qemu/{e.vmid}/config", auth: auth)
        ).ToList();
        var configResults = await Task.WhenAll(configTasks);

        // Filter to SPICE-enabled VMs, then fetch snapshots in parallel
        var spiceVms = new List<(int vmid, string name, string status, string nodeName, string pool)>();
        for (int i = 0; i < vmEntries.Count; i++)
        {
            bool hasSpice = false;
            if (configResults[i]?.TryGetProperty("data", out var cfgData) == true)
            {
                foreach (var prop in cfgData.EnumerateObject())
                {
                    if (prop.Name.StartsWith("vga") &&
                        prop.Value.GetString()?.Contains("qxl") == true)
                    {
                        hasSpice = true;
                        break;
                    }
                }
            }
            if (hasSpice) spiceVms.Add(vmEntries[i]);
        }

        var snapTasks = spiceVms.Select(e =>
            ProxmoxApi.RequestAsync(cluster.Host,
                $"/api2/json/nodes/{e.nodeName}/qemu/{e.vmid}/snapshot", auth: auth)
        ).ToList();
        var snapResults = await Task.WhenAll(snapTasks);

        var vms = new List<VmDisplayItem>();
        for (int i = 0; i < spiceVms.Count; i++)
        {
            var e = spiceVms[i];
            int snapCount = 0;
            if (snapResults[i]?.TryGetProperty("data", out var snapData) == true)
            {
                snapCount = snapData.EnumerateArray()
                    .Count(s => s.TryGetProperty("name", out var sn) &&
                                sn.GetString() != "current");
            }

            vms.Add(new VmDisplayItem
            {
                VmId = e.vmid,
                Name = e.name,
                Node = e.nodeName,
                Pool = e.pool,
                Status = e.status,
                SnapCount = snapCount,
                Notes = LookupVmNote(e.vmid) ?? "",
            });
        }

        _vmItems.Clear();
        foreach (var vm in vms.OrderBy(v => v.VmId))
            _vmItems.Add(vm);

        _clusterStatus[cluster.Name] = (true, vms.Count);
        RefreshClusterList();
        StatusLabel.Text = $"{vms.Count} SPICE-enabled VM(s) on {cluster.Name}";
    }

    private void OnRefresh(object sender, RoutedEventArgs e) => _ = RefreshVmsAsync();

    // ── VM Actions ─────────────────────────────────────────────────────────
    private List<VmDisplayItem> GetSelectedVms()
    {
        var visible = (_vmView?.OfType<VmDisplayItem>() ?? _vmItems).ToHashSet();
        var checked_ = _vmItems.Where(v => v.IsChecked && visible.Contains(v)).ToList();
        if (checked_.Count > 0) return checked_;

        if (VmGrid.SelectedItem is VmDisplayItem selected)
            return [selected];

        return [];
    }

    private async Task VmActionAsync(string action, string confirmMsg)
    {
        var vms = GetSelectedVms();
        if (vms.Count == 0)
        {
            MessageBox.Show("Select one or more VMs first.", "No Selection",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        if (MessageBox.Show(confirmMsg, "Confirm", MessageBoxButton.YesNo,
            MessageBoxImage.Question) != MessageBoxResult.Yes)
            return;

        if (_selectedClusterIdx < 0) return;
        var cluster = _config.Clusters[_selectedClusterIdx];
        var auth = await GetAuthAsync(cluster);
        if (auth == null) return;

        foreach (var vm in vms)
        {
            var endpoint = $"/api2/json/nodes/{vm.Node}/qemu/{vm.VmId}/status/{action}";
            await ProxmoxApi.RequestAsync(cluster.Host, endpoint, "POST", auth);
        }

        StatusLabel.Text = $"{action} sent to {vms.Count} VM(s). Refreshing...";
        await Task.Delay(3000);
        await RefreshVmsAsync();
    }

    private void OnStartVm(object sender, RoutedEventArgs e)
        => _ = VmActionAsync("start", "Start selected VM(s)?");

    private void OnShutdownVm(object sender, RoutedEventArgs e)
        => _ = VmActionAsync("shutdown", "Send ACPI shutdown to selected VM(s)?");

    private void OnRebootVm(object sender, RoutedEventArgs e)
        => _ = VmActionAsync("reboot", "Reboot selected VM(s)?");

    private void OnForceStopVm(object sender, RoutedEventArgs e)
        => _ = VmActionAsync("stop", "Force stop selected VM(s)?\nUnsaved data will be lost.");

    // ── SPICE Launch ───────────────────────────────────────────────────────
    private async void OnLaunchSpice(object sender, RoutedEventArgs e)
    {
        var vms = GetSelectedVms();
        if (vms.Count == 0)
        {
            MessageBox.Show("Select a VM to launch.", "No Selection",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        var viewer = ViewerService.FindRemoteViewer();
        if (viewer == null)
        {
            MessageBox.Show("remote-viewer.exe not found.\nInstall virt-viewer from spice-space.org.",
                "Missing Dependency", MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        if (_selectedClusterIdx < 0) return;
        var cluster = _config.Clusters[_selectedClusterIdx];
        var auth = await GetAuthAsync(cluster);
        if (auth == null) return;

        foreach (var vm in vms.Where(v => v.IsRunning))
        {
            StatusLabel.Text = $"Requesting SPICE proxy for {vm.Name}...";

            var proxyJson = await ProxmoxApi.RequestAsync(
                cluster.Host,
                $"/api2/json/nodes/{vm.Node}/qemu/{vm.VmId}/spiceproxy",
                "POST", auth);

            if (proxyJson?.TryGetProperty("data", out var data) != true)
            {
                StatusLabel.Text = $"Failed to get SPICE proxy for VM {vm.VmId}";
                continue;
            }

            var vvContent = "[virt-viewer]\n";
            foreach (var prop in data.EnumerateObject())
            {
                var key = prop.Name.Replace("_", "-");
                var val = prop.Value.ValueKind == System.Text.Json.JsonValueKind.Number
                    ? prop.Value.GetRawText()
                    : prop.Value.GetString() ?? "";
                vvContent += $"{key}={val}\n";
            }
            vvContent += "delete-this-file=1\n";

            var vvPath = Path.Combine(Path.GetTempPath(), $"pve-spice-{vm.VmId}.vv");
            await File.WriteAllTextAsync(vvPath, vvContent);

            ViewerService.LaunchSpice(viewer, vvPath);
            StatusLabel.Text = $"Launched SPICE session for {vm.Name}";
        }
    }

    private void OnNameDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (e.ClickCount == 2 && sender is FrameworkElement fe &&
            fe.DataContext is VmDisplayItem vm && vm.IsRunning)
        {
            OnLaunchSpice(sender, new RoutedEventArgs());
        }
    }

    private void OnVmSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        var count = _vmItems.Count(v => v.IsChecked);
        CheckCountLabel.Text = count > 0 ? $"{count} checked" : "";
    }

    private void OnSelectAllCheckBox(object sender, RoutedEventArgs e)
    {
        if (sender is not System.Windows.Controls.CheckBox cb) return;
        bool check = cb.IsChecked == true;
        foreach (var item in _vmView?.OfType<VmDisplayItem>() ?? [])
            item.IsChecked = check;
        var count = _vmItems.Count(v => v.IsChecked);
        CheckCountLabel.Text = count > 0 ? $"{count} checked" : "";
    }

    // ── Snapshots ──────────────────────────────────────────────────────────
    private async void OnSnapshots(object sender, RoutedEventArgs e)
    {
        var vms = GetSelectedVms();
        if (vms.Count != 1)
        {
            MessageBox.Show("Select exactly one VM.", "Snapshots",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        if (_selectedClusterIdx < 0) return;
        var cluster = _config.Clusters[_selectedClusterIdx];
        var auth = await GetAuthAsync(cluster);
        if (auth == null) return;

        var dlg = new Dialogs.SnapshotDialog(vms[0], cluster, auth) { Owner = this };
        dlg.ShowDialog();
        _ = RefreshVmsAsync();
    }

    private async void OnQuickRollback(object sender, RoutedEventArgs e)
    {
        var vms = GetSelectedVms();
        if (vms.Count != 1)
        {
            MessageBox.Show("Select exactly one VM.", "Quick Rollback",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        if (_selectedClusterIdx < 0) return;
        var cluster = _config.Clusters[_selectedClusterIdx];
        var auth = await GetAuthAsync(cluster);
        if (auth == null) return;

        var vm = vms[0];
        var snapJson = await ProxmoxApi.RequestAsync(
            cluster.Host,
            $"/api2/json/nodes/{vm.Node}/qemu/{vm.VmId}/snapshot",
            auth: auth);

        if (snapJson?.TryGetProperty("data", out var snapData) != true)
        {
            MessageBox.Show("Failed to load snapshots.", "Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }

        var latest = snapData.EnumerateArray()
            .Where(s => s.TryGetProperty("name", out var n) && n.GetString() != "current")
            .OrderByDescending(s => s.TryGetProperty("snaptime", out var t) ? t.GetInt64() : 0)
            .FirstOrDefault();

        if (latest.ValueKind == JsonValueKind.Undefined)
        {
            MessageBox.Show("No snapshots found.", "Quick Rollback",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        var snapName = latest.GetProperty("name").GetString()!;
        if (MessageBox.Show($"Rollback VM {vm.VmId} to '{snapName}'?\nCurrent state will be lost.",
            "Confirm Rollback", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
            return;

        await ProxmoxApi.RequestAsync(
            cluster.Host,
            $"/api2/json/nodes/{vm.Node}/qemu/{vm.VmId}/snapshot/{Uri.EscapeDataString(snapName)}/rollback",
            "POST", auth);

        StatusLabel.Text = $"Rolled back to '{snapName}'";
        await Task.Delay(3000);
        await RefreshVmsAsync();
    }

    // ── Import / Export ────────────────────────────────────────────────────
    private void OnImport(object sender, RoutedEventArgs e)
    {
        var dlg = new Microsoft.Win32.OpenFileDialog
        {
            Filter = "JSON files|*.json",
            Title = "Import Cluster Configuration",
        };
        if (dlg.ShowDialog() != true) return;

        try
        {
            var json = File.ReadAllText(dlg.FileName);
            var imported = JsonSerializer.Deserialize<AppConfig>(json);
            if (imported?.Clusters == null || imported.Clusters.Count == 0)
            {
                MessageBox.Show("No clusters found in file.", "Import",
                    MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            var existingNames = _config.Clusters.Select(c => c.Name).ToHashSet();
            foreach (var cluster in imported.Clusters)
            {
                if (existingNames.Contains(cluster.Name))
                    cluster.Name += " (Imported)";
                _config.Clusters.Add(cluster);
            }

            SaveConfig();
            RefreshClusterList();
            StatusLabel.Text = $"Imported {imported.Clusters.Count} cluster(s)";
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Import failed: {ex.Message}", "Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    private void OnExport(object sender, RoutedEventArgs e)
    {
        if (_config.Clusters.Count == 0)
        {
            MessageBox.Show("No clusters to export.", "Export",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        var result = MessageBox.Show(
            "Warning: exported file will contain plaintext secrets.\nContinue?",
            "Export", MessageBoxButton.YesNo, MessageBoxImage.Warning);
        if (result != MessageBoxResult.Yes) return;

        var dlg = new Microsoft.Win32.SaveFileDialog
        {
            Filter = "JSON files|*.json",
            FileName = "proxmox-spice-export.json",
            Title = "Export Cluster Configuration",
        };
        if (dlg.ShowDialog() != true) return;

        try
        {
            var export = new AppConfig { Clusters = [] };
            foreach (var cluster in _config.Clusters)
            {
                var copy = JsonSerializer.Deserialize<ClusterConfig>(
                    JsonSerializer.Serialize(cluster))!;
                // Decrypt for export
                var secret = ConfigService.GetSecret(cluster);
                if (secret != null)
                    copy.TokenSecretEnc = secret; // plaintext in export
                export.Clusters.Add(copy);
            }

            var json = JsonSerializer.Serialize(export, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(dlg.FileName, json);
            StatusLabel.Text = "Configuration exported";
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Export failed: {ex.Message}", "Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    // ── Header buttons ─────────────────────────────────────────────────────
    private void OnGitHubClick(object sender, RoutedEventArgs e)
        => Process.Start(new ProcessStartInfo("https://github.com/darthrater78/proxmoxspicemanager") { UseShellExecute = true });

    private void OnReleaseNotesClick(object sender, RoutedEventArgs e)
        => Process.Start(new ProcessStartInfo("https://github.com/darthrater78/proxmoxspicemanager/releases/tag/v2.2.3") { UseShellExecute = true });

    private void OnCheckPrereqs(object sender, RoutedEventArgs e)
    {
        var viewer = ViewerService.FindRemoteViewer();
        if (viewer != null)
            MessageBox.Show("All prerequisites are installed.", "All Good",
                MessageBoxButton.OK, MessageBoxImage.Information);
        else
            MessageBox.Show("remote-viewer.exe not found.\nDownload virt-viewer from spice-space.org.",
                "Missing Dependency", MessageBoxButton.OK, MessageBoxImage.Warning);
    }

    // ── Notes ──────────────────────────────────────────────────────────────
    private string VmNoteKey(int vmid)
    {
        if (_selectedClusterIdx >= 0 && _selectedClusterIdx < _config.Clusters.Count)
            return $"{_config.Clusters[_selectedClusterIdx].Name}:{vmid}";
        return vmid.ToString();
    }

    private string? LookupVmNote(int vmid)
    {
        _config.VmNotes ??= new Dictionary<string, string>();
        var compositeKey = VmNoteKey(vmid);
        if (_config.VmNotes.TryGetValue(compositeKey, out var note))
            return note;
        // Backward compat: fall back to plain vmid key
        if (_config.VmNotes.TryGetValue(vmid.ToString(), out var legacyNote))
            return legacyNote;
        return null;
    }

    private void SaveVmNote(VmDisplayItem vm)
    {
        _config.VmNotes ??= new Dictionary<string, string>();
        var key = VmNoteKey(vm.VmId);
        // Remove legacy plain-vmid key if present
        _config.VmNotes.Remove(vm.VmId.ToString());
        if (string.IsNullOrWhiteSpace(vm.Notes))
            _config.VmNotes.Remove(key);
        else
            _config.VmNotes[key] = vm.Notes;

        if (!string.IsNullOrWhiteSpace(vm.Notes))
        {
            _config.NoteOptions ??= [];
            if (!_config.NoteOptions.Contains(vm.Notes))
                _config.NoteOptions.Add(vm.Notes);
        }

        SaveConfig();
    }

    private void OnNotesComboLoaded(object sender, RoutedEventArgs e)
    {
        if (sender is ComboBox combo)
        {
            combo.ItemsSource = _config.NoteOptions ?? [];
            combo.IsDropDownOpen = true;
        }
    }

    private void OnNotesComboLostFocus(object sender, RoutedEventArgs e)
    {
        if (sender is ComboBox combo && combo.DataContext is VmDisplayItem vm)
        {
            var newText = combo.Text?.Trim() ?? "";
            if (vm.Notes != newText)
            {
                vm.Notes = newText;
                SaveVmNote(vm);
            }
        }
    }

    private void OnManageNotes(object sender, RoutedEventArgs e)
    {
        _config.NoteOptions ??= [];
        var dlg = new Dialogs.ManageNotesDialog(_config.NoteOptions) { Owner = this };
        if (dlg.ShowDialog() == true)
        {
            _config.NoteOptions = dlg.GetOptions();
            SaveConfig();
        }
    }

    // ── Column Filtering ──────────────────────────────────────────────────
    private bool VmFilterPredicate(object obj)
    {
        if (obj is not VmDisplayItem vm) return false;
        foreach (var kvp in _activeFilters)
        {
            var val = kvp.Value;
            if (string.IsNullOrEmpty(val)) continue;

            string field = kvp.Key.ToLowerInvariant() switch
            {
                "name" => vm.Name,
                "node" => vm.Node,
                "pool" => vm.Pool,
                "status" => vm.Status,
                "notes" => vm.Notes,
                _ => ""
            };

            if (kvp.Key.Equals("name", StringComparison.OrdinalIgnoreCase))
            {
                // Substring search for name
                if (!field.Contains(val, StringComparison.OrdinalIgnoreCase))
                    return false;
            }
            else
            {
                // Exact match for other columns
                if (!field.Equals(val, StringComparison.OrdinalIgnoreCase))
                    return false;
            }
        }
        return true;
    }

    private void OnColumnHeaderRightClick(object sender, MouseButtonEventArgs e)
    {
        if (e.OriginalSource is not FrameworkElement fe) return;

        // Walk up to find the DataGridColumnHeader
        var header = FindParent<DataGridColumnHeader>(fe);
        if (header?.Column == null) return;

        var colName = GetColumnFieldName(header.Column);
        if (colName == null) return;

        ShowFilterPopup(header, colName);
    }

    private static T? FindParent<T>(DependencyObject child) where T : DependencyObject
    {
        var parent = System.Windows.Media.VisualTreeHelper.GetParent(child);
        while (parent != null)
        {
            if (parent is T t) return t;
            parent = System.Windows.Media.VisualTreeHelper.GetParent(parent);
        }
        return null;
    }

    private string? GetColumnFieldName(DataGridColumn col)
    {
        if (col is DataGridBoundColumn bound && bound.Binding is Binding b)
            return b.Path?.Path;
        if (col is DataGridTemplateColumn tmpl)
        {
            var sort = tmpl.SortMemberPath;
            if (!string.IsNullOrEmpty(sort)) return sort;
        }
        // Fallback: match by header text
        var hdr = col.Header?.ToString()?.Trim() ?? "";
        // Strip filter indicator
        hdr = hdr.Replace(" \U0001f53d", "");
        return hdr.ToLowerInvariant() switch
        {
            "name" => "Name",
            "node" => "Node",
            "pool" => "Pool",
            "status" => "Status",
            "notes" => "Notes",
            _ => null
        };
    }

    private void ShowFilterPopup(DataGridColumnHeader header, string colName)
    {
        var popup = new Popup
        {
            PlacementTarget = header,
            Placement = PlacementMode.Bottom,
            StaysOpen = false,
            AllowsTransparency = true,
        };

        var border = new Border
        {
            Background = (System.Windows.Media.Brush)FindResource("ThemeSurface0"),
            BorderBrush = (System.Windows.Media.Brush)FindResource("ThemeSurface2"),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(4),
            Padding = new Thickness(10),
            MinWidth = 180,
        };

        var panel = new StackPanel();

        var title = new TextBlock
        {
            Text = $"Filter: {colName.ToUpper()}",
            Foreground = (System.Windows.Media.Brush)FindResource("ThemeSubtext0"),
            FontSize = 11,
            FontWeight = FontWeights.Bold,
            Margin = new Thickness(0, 0, 0, 6),
        };
        panel.Children.Add(title);

        if (colName.Equals("Name", StringComparison.OrdinalIgnoreCase))
        {
            // Text input for substring search
            var textBox = new TextBox
            {
                Text = _activeFilters.GetValueOrDefault(colName, ""),
                Background = (System.Windows.Media.Brush)FindResource("ThemeSurface1"),
                Foreground = (System.Windows.Media.Brush)FindResource("ThemeText"),
                CaretBrush = (System.Windows.Media.Brush)FindResource("ThemeText"),
                BorderThickness = new Thickness(1),
                BorderBrush = (System.Windows.Media.Brush)FindResource("ThemeSurface2"),
                Padding = new Thickness(6, 4, 6, 4),
                FontSize = 12,
                MinWidth = 150,
            };
            panel.Children.Add(textBox);

            var btnPanel = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 8, 0, 0) };

            var applyBtn = new Button
            {
                Content = "Apply",
                Padding = new Thickness(10, 4, 10, 4),
                Background = (System.Windows.Media.Brush)FindResource("ThemeBlue"),
                Foreground = (System.Windows.Media.Brush)FindResource("ThemeCrust"),
                BorderThickness = new Thickness(0),
                Cursor = Cursors.Hand,
                Margin = new Thickness(0, 0, 6, 0),
            };
            applyBtn.Click += (_, _) =>
            {
                var val = textBox.Text.Trim();
                if (string.IsNullOrEmpty(val))
                    _activeFilters.Remove(colName);
                else
                    _activeFilters[colName] = val;
                ApplyFilters();
                UpdateColumnHeaders();
                popup.IsOpen = false;
            };
            btnPanel.Children.Add(applyBtn);

            var clearBtn = new Button
            {
                Content = "Clear",
                Padding = new Thickness(10, 4, 10, 4),
                Background = (System.Windows.Media.Brush)FindResource("ThemeSurface1"),
                Foreground = (System.Windows.Media.Brush)FindResource("ThemeText"),
                BorderThickness = new Thickness(0),
                Cursor = Cursors.Hand,
            };
            clearBtn.Click += (_, _) =>
            {
                _activeFilters.Remove(colName);
                ApplyFilters();
                UpdateColumnHeaders();
                popup.IsOpen = false;
            };
            btnPanel.Children.Add(clearBtn);

            panel.Children.Add(btnPanel);
        }
        else
        {
            // ComboBox with distinct values
            var distinctValues = _vmItems
                .Select(vm => colName switch
                {
                    "Node" => vm.Node,
                    "Pool" => vm.Pool,
                    "Status" => vm.Status,
                    "Notes" => vm.Notes,
                    _ => ""
                })
                .Where(v => !string.IsNullOrEmpty(v))
                .Distinct()
                .OrderBy(v => v)
                .ToList();

            distinctValues.Insert(0, "All");

            var combo = new ComboBox
            {
                ItemsSource = distinctValues,
                SelectedItem = _activeFilters.ContainsKey(colName) ? _activeFilters[colName] : "All",
                Background = (System.Windows.Media.Brush)FindResource("ThemeSurface1"),
                Foreground = (System.Windows.Media.Brush)FindResource("ThemeText"),
                BorderThickness = new Thickness(1),
                BorderBrush = (System.Windows.Media.Brush)FindResource("ThemeSurface2"),
                FontSize = 12,
                MinWidth = 150,
            };
            combo.SelectionChanged += (_, _) =>
            {
                if (combo.SelectedItem is string val)
                {
                    if (val == "All")
                        _activeFilters.Remove(colName);
                    else
                        _activeFilters[colName] = val;
                    ApplyFilters();
                    UpdateColumnHeaders();
                    popup.IsOpen = false;
                }
            };
            panel.Children.Add(combo);

            var clearBtn = new Button
            {
                Content = "Clear",
                Padding = new Thickness(10, 4, 10, 4),
                Background = (System.Windows.Media.Brush)FindResource("ThemeSurface1"),
                Foreground = (System.Windows.Media.Brush)FindResource("ThemeText"),
                BorderThickness = new Thickness(0),
                Cursor = Cursors.Hand,
                Margin = new Thickness(0, 8, 0, 0),
            };
            clearBtn.Click += (_, _) =>
            {
                _activeFilters.Remove(colName);
                ApplyFilters();
                UpdateColumnHeaders();
                popup.IsOpen = false;
            };
            panel.Children.Add(clearBtn);
        }

        border.Child = panel;
        popup.Child = border;
        popup.IsOpen = true;
    }

    private void ApplyFilters()
    {
        _vmView?.Refresh();
        ClearAllFiltersBtn.Visibility = _activeFilters.Count > 0
            ? Visibility.Visible
            : Visibility.Collapsed;
    }

    private void UpdateColumnHeaders()
    {
        foreach (var col in VmGrid.Columns)
        {
            var fieldName = GetColumnFieldName(col);
            if (fieldName == null) continue;

            var baseName = fieldName.ToUpperInvariant();
            if (_activeFilters.ContainsKey(fieldName))
                col.Header = $"{baseName} \U0001f53d";
            else
                col.Header = baseName;
        }
    }

    private void OnClearAllFilters(object sender, RoutedEventArgs e)
    {
        _activeFilters.Clear();
        ApplyFilters();
        UpdateColumnHeaders();
    }

    private void OnCreateShortcut(object sender, RoutedEventArgs e)
    {
        try
        {
            var startMenu = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "Microsoft", "Windows", "Start Menu", "Programs");
            Directory.CreateDirectory(startMenu);

            var shortcutPath = Path.Combine(startMenu, "Proxmox SPICE Manager.lnk");
            var exePath = Environment.ProcessPath ?? Process.GetCurrentProcess().MainModule?.FileName ?? "";

            var psScript = $@"
$sc = '{shortcutPath.Replace("'", "''")}'
$exe = '{exePath.Replace("'", "''")}'
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($sc)
$s.TargetPath = $exe
$s.WorkingDirectory = '{Path.GetDirectoryName(exePath)?.Replace("'", "''")}'
$s.Description = 'Proxmox SPICE Connection Manager'
$s.Save()";

            var encoded = Convert.ToBase64String(System.Text.Encoding.Unicode.GetBytes(psScript));
            Process.Start(new ProcessStartInfo
            {
                FileName = "powershell",
                Arguments = $"-EncodedCommand {encoded}",
                CreateNoWindow = true,
                UseShellExecute = false,
            })?.WaitForExit(10000);

            MessageBox.Show("Shortcut created in Start Menu.", "Done",
                MessageBoxButton.OK, MessageBoxImage.Information);
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Failed to create shortcut: {ex.Message}", "Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
}
