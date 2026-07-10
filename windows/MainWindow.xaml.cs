using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
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

    public MainWindow()
    {
        InitializeComponent();
        _config = ConfigService.Load();
        ConfigService.MigrateSecrets(_config);

        ThemeCombo.ItemsSource = Themes.All.Keys.ToList();
        ThemeCombo.SelectedItem = _config.Theme;

        VmGrid.ItemsSource = _vmItems;
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
    private AuthInfo? GetAuth(ClusterConfig cluster)
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

        var authResult = ProxmoxApi.AuthenticatePasswordAsync(
            cluster.Host, cluster.Username, pwDlg.Password, cluster.SkipTlsVerify).Result;

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

        var auth = GetAuth(cluster);
        if (auth == null)
        {
            _clusterStatus[cluster.Name] = (false, null);
            RefreshClusterList();
            return;
        }

        var nodesJson = await ProxmoxApi.RequestAsync(
            cluster.Host, "/api2/json/nodes", auth: auth);

        if (nodesJson == null || !nodesJson.Value.TryGetProperty("data", out var nodesData))
        {
            StatusLabel.Text = $"Failed to connect to {cluster.Name}";
            _clusterStatus[cluster.Name] = (false, null);
            RefreshClusterList();
            return;
        }

        var vms = new List<VmDisplayItem>();

        foreach (var node in nodesData.EnumerateArray())
        {
            var nodeName = node.GetProperty("node").GetString() ?? "";
            var vmJson = await ProxmoxApi.RequestAsync(
                cluster.Host, $"/api2/json/nodes/{nodeName}/qemu", auth: auth);

            if (vmJson == null || !vmJson.Value.TryGetProperty("data", out var vmData))
                continue;

            foreach (var vm in vmData.EnumerateArray())
            {
                var vmid = vm.GetProperty("vmid").GetInt32();
                var name = vm.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "";
                var status = vm.TryGetProperty("status", out var s) ? s.GetString() ?? "" : "";
                var pool = vm.TryGetProperty("pool", out var p) ? p.GetString() ?? "" : "";

                // Check for SPICE display
                var configJson = await ProxmoxApi.RequestAsync(
                    cluster.Host,
                    $"/api2/json/nodes/{nodeName}/qemu/{vmid}/config",
                    auth: auth);

                bool hasSpice = false;
                if (configJson?.TryGetProperty("data", out var cfgData) == true)
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
                if (!hasSpice) continue;

                // Get snapshot count
                int snapCount = 0;
                var snapJson = await ProxmoxApi.RequestAsync(
                    cluster.Host,
                    $"/api2/json/nodes/{nodeName}/qemu/{vmid}/snapshot",
                    auth: auth);
                if (snapJson?.TryGetProperty("data", out var snapData) == true)
                {
                    snapCount = snapData.EnumerateArray()
                        .Count(s => s.TryGetProperty("name", out var sn) &&
                                    sn.GetString() != "current");
                }

                var noteText = cluster.Notes?.GetValueOrDefault(vmid.ToString()) ?? "";

                vms.Add(new VmDisplayItem
                {
                    VmId = vmid,
                    Name = name,
                    Node = nodeName,
                    Pool = pool,
                    Status = status,
                    SnapCount = snapCount,
                    Notes = noteText,
                });
            }
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
        var checked_ = _vmItems.Where(v => v.IsChecked).ToList();
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
        var auth = GetAuth(cluster);
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
        var auth = GetAuth(cluster);
        if (auth == null) return;

        foreach (var vm in vms.Where(v => v.IsRunning))
        {
            var proxyJson = await ProxmoxApi.RequestAsync(
                cluster.Host,
                $"/api2/json/nodes/{vm.Node}/qemu/{vm.VmId}/spiceproxy",
                "POST", auth, $"proxy={cluster.Host.Replace("https://", "").Split(':')[0]}");

            if (proxyJson?.TryGetProperty("data", out var data) != true)
            {
                StatusLabel.Text = $"Failed to get SPICE proxy for VM {vm.VmId}";
                continue;
            }

            var vvContent = "[virt-viewer]\n";
            foreach (var prop in data.EnumerateObject())
                vvContent += $"{prop.Name.Replace("_", "-")}={prop.Value.GetString()}\n";
            vvContent += "delete-this-file=1\n";

            var vvPath = Path.Combine(Path.GetTempPath(), $"pve-spice-{vm.VmId}.vv");
            await File.WriteAllTextAsync(vvPath, vvContent);

            ViewerService.LaunchSpice(viewer, vvPath);
            StatusLabel.Text = $"Launched SPICE session for {vm.Name}";
        }
    }

    private void OnVmDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (VmGrid.SelectedItem is VmDisplayItem vm && vm.IsRunning)
            OnLaunchSpice(sender, new RoutedEventArgs());
    }

    private void OnVmSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        var count = _vmItems.Count(v => v.IsChecked);
        CheckCountLabel.Text = count > 0 ? $"{count} checked" : "";
    }

    // ── Snapshots ──────────────────────────────────────────────────────────
    private void OnSnapshots(object sender, RoutedEventArgs e)
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
        var auth = GetAuth(cluster);
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
        var auth = GetAuth(cluster);
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
