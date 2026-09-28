using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
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
    private string? _loadedClusterName;

    // Single source of truth for the version is <Version> in the csproj.
    private static readonly string AppVersion =
        typeof(MainWindow).Assembly.GetName().Version?.ToString(3) ?? "0.0.0";

    public MainWindow()
    {
        InitializeComponent();
        Title = $"Proxmox SPICE Manager v{AppVersion}";
        VersionText.Text = $"for Proxmox VE · v{AppVersion}";
        _config = ConfigService.Load();
        _config.NoteOptions ??= [];
        _config.VmNotes ??= new Dictionary<string, string>();
        ConfigService.MigrateSecrets(_config);

        VmList.ItemsSource = _vmItems;
        _vmView = CollectionViewSource.GetDefaultView(_vmItems);
        _vmView.Filter = VmFilterPredicate;
        _vmView.GroupDescriptions.Add(new PropertyGroupDescription(nameof(VmDisplayItem.Node)));
        _vmView.SortDescriptions.Add(new SortDescription(nameof(VmDisplayItem.Node), ListSortDirection.Ascending));
        _vmView.SortDescriptions.Add(new SortDescription(nameof(VmDisplayItem.VmId), ListSortDirection.Ascending));

        RefreshClusterList();
        UpdateListState();
        UpdateInspector();

        if (_config.Clusters.Count > 0)
        {
            _selectedClusterIdx = 0;
            RefreshClusterList();
            Loaded += async (_, _) => await RefreshVmsAsync();
        }
    }

    private void SaveConfig()
    {
        _config.Version = "1.0.0";
        ConfigService.Save(_config);
    }

    // ── Appearance ─────────────────────────────────────────────────────────
    private void OnOpenAppearance(object sender, RoutedEventArgs e)
    {
        RefreshAppearanceChoices();
        // Line the flyout up with the sidebar rather than with the small button
        AppearancePopup.HorizontalOffset = -AppearanceBtn.TranslatePoint(new Point(0, 0), this).X;
        AppearancePopup.IsOpen = true;
    }

    private void RefreshAppearanceChoices()
    {
        ThemeChoices.ItemsSource = Themes.All.Values.Select(t => new ThemeChoice
        {
            Name = t.Name,
            Crust = new SolidColorBrush(t.Crust),
            Base = new SolidColorBrush(t.Base),
            Surface = new SolidColorBrush(t.Surface1),
            Text = new SolidColorBrush(t.Subtext0),
            Accent = new SolidColorBrush(Themes.AccentColor(t, ThemeManager.CurrentAccent)),
            IsSelected = t.Name == ThemeManager.Current.Name,
        }).ToList();
        AccentChoices.ItemsSource = Themes.Accents.Keys.Select(a => new AccentChoice
        {
            Name = a,
            Brush = new SolidColorBrush(Themes.AccentColor(ThemeManager.Current, a)),
            IsSelected = a == ThemeManager.CurrentAccent,
        }).ToList();
        AccentName.Text = ThemeManager.CurrentAccent == Themes.DefaultAccent
            ? $"{Themes.DefaultAccent} (default)"
            : ThemeManager.CurrentAccent;
    }

    private void OnThemeChoice(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is not ThemeChoice choice) return;
        _config.Theme = choice.Name;
        ApplyAppearance();
    }

    private void OnAccentChoice(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is not AccentChoice choice) return;
        _config.Accent = choice.Name;
        ApplyAppearance();
    }

    private void ApplyAppearance()
    {
        ThemeManager.Apply(_config.Theme, _config.Accent);
        SaveConfig();
        RefreshClusterList();
        RefreshAppearanceChoices();
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
        if (sender is not FrameworkElement fe || fe.DataContext is not ClusterListItem item) return;
        _selectedClusterIdx = item.Index;
        RefreshClusterList();
        if (e.ClickCount == 2)
            EditCluster();
        else
            _ = RefreshVmsAsync();
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

    private void EditCluster()
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

    private void RemoveCluster()
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
        _loadedClusterName = null;
        RefreshClusterList();
        UpdateListState();
        if (_selectedClusterIdx >= 0)
            _ = RefreshVmsAsync();
        else
        {
            ClusterTitle.Text = "No cluster";
            StatusLabel.Text = "Add a cluster to get started";
        }
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
        ClusterTitle.Text = cluster.Name;
        if (_loadedClusterName != cluster.Name)
        {
            // Don't leave another cluster's VMs on screen under this cluster's name
            _vmItems.Clear();
            UpdateListState();
        }
        StatusLabel.Text = $"Loading VMs from {cluster.Name}...";
        var totalSw = DebugLogger.StartTimer($"RefreshVmsAsync for {cluster.Name}");

        try
        {
            var auth = await GetAuthAsync(cluster);
            if (auth == null)
            {
                DebugLogger.Log("[Refresh] Auth failed — aborting refresh");
                _clusterStatus[cluster.Name] = (false, null);
                RefreshClusterList();
                return;
            }

            // Phase 1: Fetch pool memberships and node list in parallel
            var phaseSw = DebugLogger.StartTimer("Phase 1: cluster/resources + nodes");
            var resourcesTask = ProxmoxApi.RequestAsync(
                cluster.Host, "/api2/json/cluster/resources?type=vm", auth: auth);
            var nodesTask = ProxmoxApi.RequestAsync(
                cluster.Host, "/api2/json/nodes", auth: auth);
            await Task.WhenAll(resourcesTask, nodesTask);
            DebugLogger.StopTimer(phaseSw, "Phase 1: cluster/resources + nodes");

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

            // Phase 2: Fetch per-node VM lists in parallel
            var nodeNames = nodesData.EnumerateArray()
                .Select(n => n.GetProperty("node").GetString() ?? "")
                .Where(n => n.Length > 0)
                .ToList();

            phaseSw = DebugLogger.StartTimer($"Phase 2: per-node VM lists ({nodeNames.Count} nodes)");
            var nodeVmTasks = nodeNames.Select(nodeName =>
                ProxmoxApi.RequestAsync(cluster.Host, $"/api2/json/nodes/{nodeName}/qemu", auth: auth)
            ).ToList();
            var nodeVmResults = await Task.WhenAll(nodeVmTasks);
            DebugLogger.StopTimer(phaseSw, $"Phase 2: per-node VM lists ({nodeNames.Count} nodes)");

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

            DebugLogger.Log($"[Refresh] Found {vmEntries.Count} total VMs across {nodeNames.Count} nodes");

            // Phase 3: Fetch config for all VMs in parallel to check for SPICE display
            phaseSw = DebugLogger.StartTimer($"Phase 3: VM configs ({vmEntries.Count} VMs)");
            var configTasks = vmEntries.Select(e =>
                ProxmoxApi.RequestAsync(cluster.Host,
                    $"/api2/json/nodes/{e.nodeName}/qemu/{e.vmid}/config", auth: auth)
            ).ToList();
            var configResults = await Task.WhenAll(configTasks);
            DebugLogger.StopTimer(phaseSw, $"Phase 3: VM configs ({vmEntries.Count} VMs)");

            var spiceVms = new List<(int vmid, string name, string status, string nodeName, string pool, bool hasAgent, string osType)>();
            for (int i = 0; i < vmEntries.Count; i++)
            {
                bool hasSpice = false;
                bool hasAgent = false;
                string osType = "";
                if (configResults[i]?.TryGetProperty("data", out var cfgData) == true)
                {
                    foreach (var prop in cfgData.EnumerateObject())
                    {
                        if (prop.Name.StartsWith("vga") &&
                            prop.Value.GetString()?.Contains("qxl") == true)
                            hasSpice = true;
                        if (prop.Name == "agent" &&
                            prop.Value.GetString()?.StartsWith("1") == true)
                            hasAgent = true;
                        if (prop.Name == "ostype")
                            osType = prop.Value.GetString() ?? "";
                    }
                }
                if (hasSpice) spiceVms.Add((vmEntries[i].vmid, vmEntries[i].name,
                    vmEntries[i].status, vmEntries[i].nodeName, vmEntries[i].pool, hasAgent, osType));
            }

            DebugLogger.Log($"[Refresh] {spiceVms.Count} SPICE-enabled VMs found");

            // Phase 4a: Fetch snapshots (fast, required)
            phaseSw = DebugLogger.StartTimer($"Phase 4a: snapshots ({spiceVms.Count})");
            var snapTasks = spiceVms.Select(e =>
                ProxmoxApi.RequestAsync(cluster.Host,
                    $"/api2/json/nodes/{e.nodeName}/qemu/{e.vmid}/snapshot", auth: auth)
            ).ToList();
            var snapResults = await Task.WhenAll(snapTasks);
            DebugLogger.StopTimer(phaseSw, $"Phase 4a: snapshots ({spiceVms.Count})");

            // Build VM list and display immediately — IPs come later
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
                    HasAgent = e.hasAgent,
                    OsType = e.osType,
                    IpAddress = e.hasAgent ? "" : "no agent",
                    Notes = LookupVmNote(e.vmid) ?? "",
                });
            }

            // Keep the selection across the reload so actions can be followed up
            var keepSelected = GetSelectedVms().Select(v => v.VmId).ToHashSet();
            _vmItems.Clear();
            foreach (var vm in vms.OrderBy(v => v.VmId))
                _vmItems.Add(vm);
            _loadedClusterName = cluster.Name;

            _clusterStatus[cluster.Name] = (true, vms.Count);
            RefreshClusterList();
            DebugLogger.StopTimer(totalSw, $"RefreshVmsAsync for {cluster.Name} — {vms.Count} SPICE VMs");
            OnVmsLoaded(keepSelected);

            // Phase 4b: Fetch guest-agent IPs in background — only for running VMs with agent enabled
            var runningVms = _vmItems.Where(v => v.IsRunning && v.HasAgent).ToList();
            if (runningVms.Count > 0)
            {
                DebugLogger.Log($"[Refresh] Fetching IPs for {runningVms.Count} running VMs in background");
                var agentTimeout = TimeSpan.FromSeconds(3);
                int errorCount = 0;
                var ipTasks = runningVms.Select(capturedVm => Task.Run(async () =>
                {
                    try
                    {
                        var ipJson = await ProxmoxApi.RequestAsync(cluster.Host,
                            $"/api2/json/nodes/{capturedVm.Node}/qemu/{capturedVm.VmId}/agent/network-get-interfaces",
                            auth: auth, timeout: agentTimeout);

                        await Dispatcher.InvokeAsync(() =>
                        {
                            if (ipJson == null)
                            {
                                capturedVm.IpAddress = "agent error";
                                Interlocked.Increment(ref errorCount);
                            }
                            else
                            {
                                var ip = ParseIpAddress(ipJson);
                                capturedVm.IpAddress = ip.Length > 0 ? ip : "";
                            }
                        });
                    }
                    catch (Exception ex)
                    {
                        DebugLogger.Log($"[Refresh] Background IP fetch for VM {capturedVm.VmId} failed: {ex.Message}");
                        Interlocked.Increment(ref errorCount);
                        await Dispatcher.InvokeAsync(() =>
                        {
                            capturedVm.IpAddress = "agent error";
                        });
                    }
                })).ToList();

                _ = Task.WhenAll(ipTasks).ContinueWith(_ =>
                {
                    Dispatcher.InvokeAsync(() =>
                    {
                        if (errorCount > 0)
                            StatusLabel.Text = $"{ClusterSummary()} · {errorCount} agent error(s)";
                    });
                });
            }
        }
        catch (Exception ex)
        {
            DebugLogger.Log($"[Refresh] CRASHED: {ex.GetType().Name}: {ex.Message}");
            StatusLabel.Text = $"Error loading VMs: {ex.Message}";
            _clusterStatus[cluster.Name] = (false, null);
            RefreshClusterList();
        }
    }

    private static string ParseIpAddress(JsonElement? ipJson)
    {
        if (ipJson?.TryGetProperty("data", out var agentData) != true ||
            !agentData.TryGetProperty("result", out var ifaces))
            return "";

        foreach (var iface in ifaces.EnumerateArray())
        {
            var ifName = iface.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "";
            if (ifName == "lo") continue;
            if (iface.TryGetProperty("ip-addresses", out var addrs))
            {
                foreach (var addr in addrs.EnumerateArray())
                {
                    if (addr.TryGetProperty("ip-address-type", out var t) &&
                        t.GetString() == "ipv4" &&
                        addr.TryGetProperty("ip-address", out var ip))
                    {
                        return ip.GetString() ?? "";
                    }
                }
            }
        }
        return "";
    }

    private void OnRefresh(object sender, RoutedEventArgs e) => _ = RefreshVmsAsync();

    // ── List state: counts, filters, summary ──────────────────────────────
    // Called once a cluster's VMs are in _vmItems
    private void OnVmsLoaded(HashSet<int>? keepSelected = null)
    {
        UpdateListState();
        StatusLabel.Text = ClusterSummary();
        if (keepSelected is { Count: > 0 })
        {
            foreach (var vm in _vmView?.OfType<VmDisplayItem>() ?? [])
                if (keepSelected.Contains(vm.VmId))
                    VmList.SelectedItems.Add(vm);
        }
        if (VmList.SelectedItems.Count == 0)
            VmList.SelectedItem = _vmView?.OfType<VmDisplayItem>().FirstOrDefault();
    }

    private string ClusterSummary()
    {
        var nodes = _vmItems.Select(v => v.Node).Distinct().Count();
        var parts = new List<string>
        {
            _vmItems.Count == 1 ? "1 SPICE VM" : $"{_vmItems.Count} SPICE VMs",
            nodes == 1 ? "1 node" : $"{nodes} nodes",
        };
        if (_selectedClusterIdx >= 0 && _selectedClusterIdx < _config.Clusters.Count &&
            Uri.TryCreate(_config.Clusters[_selectedClusterIdx].Host, UriKind.Absolute, out var uri))
            parts.Add(uri.Host);
        return string.Join(" · ", parts);
    }

    private void UpdateListState()
    {
        var running = _vmItems.Count(v => v.IsRunning);
        FilterAll.Content = $"All  {_vmItems.Count}";
        FilterRunning.Content = $"Running  {running}";
        FilterStopped.Content = $"Stopped  {_vmItems.Count - running}";
        _vmView?.Refresh();
        var visible = _vmView?.OfType<VmDisplayItem>().Any() == true;
        EmptyText.Visibility = visible ? Visibility.Collapsed : Visibility.Visible;
        EmptyText.Text = _vmItems.Count == 0
            ? (_selectedClusterIdx < 0 ? "Add a cluster to see its VMs" : "No SPICE VMs loaded")
            : "No VMs match the filter";
    }

    private bool VmFilterPredicate(object obj)
    {
        if (obj is not VmDisplayItem vm) return false;
        if (FilterRunning.IsChecked == true && !vm.IsRunning) return false;
        if (FilterStopped.IsChecked == true && vm.IsRunning) return false;

        var q = SearchBox.Text.Trim();
        if (q.Length == 0) return true;
        return new[] { vm.Name, vm.VmId.ToString(), vm.IpAddress, vm.Node, vm.Pool, vm.Notes, vm.OsLabel }
            .Any(f => f.Contains(q, StringComparison.OrdinalIgnoreCase));
    }

    private void OnFilterChanged(object sender, RoutedEventArgs e)
    {
        if (IsLoaded) UpdateListState();
    }

    private void OnSearchChanged(object sender, TextChangedEventArgs e)
    {
        UpdateSearchHint();
        UpdateListState();
    }

    private void OnSearchFocus(object sender, KeyboardFocusChangedEventArgs e) => UpdateSearchHint();

    private void UpdateSearchHint()
    {
        var empty = SearchBox.Text.Length == 0;
        SearchHint.Visibility = empty && !SearchBox.IsKeyboardFocused ? Visibility.Visible : Visibility.Collapsed;
        SearchKey.Visibility = empty ? Visibility.Visible : Visibility.Collapsed;
    }

    // ── Keyboard ───────────────────────────────────────────────────────────
    private void OnWindowKeyDown(object sender, KeyEventArgs e)
    {
        var mods = Keyboard.Modifiers;
        if (e.Key == Key.F5)
        {
            _ = RefreshVmsAsync();
            e.Handled = true;
            return;
        }

        if (Keyboard.FocusedElement is TextBox box)
        {
            if (box == SearchBox && e.Key is Key.Escape or Key.Enter or Key.Down)
            {
                if (e.Key == Key.Escape) SearchBox.Clear();
                FocusList();
                e.Handled = true;
            }
            return;
        }

        switch (e.Key)
        {
            case Key.Oem2 or Key.Divide when mods == ModifierKeys.None:
                SearchBox.Focus();
                break;
            case Key.Enter when mods == ModifierKeys.None:
                _ = LaunchAsync(GetSelectedVms());
                break;
            case Key.S when mods == ModifierKeys.None:
                OnStartVm(this, e);
                break;
            case Key.S when mods == ModifierKeys.Shift:
                OnShutdownVm(this, e);
                break;
            case Key.R when mods == ModifierKeys.None:
                OnRebootVm(this, e);
                break;
            case Key.P when mods == ModifierKeys.None:
                OnSnapshots(this, e);
                break;
            case Key.OemPeriod when mods == ModifierKeys.Control:
                OnForceStopVm(this, e);
                break;
            default:
                return;
        }
        e.Handled = true;
    }

    private void FocusList()
    {
        if (VmList.SelectedItem == null)
            VmList.SelectedItem = _vmView?.OfType<VmDisplayItem>().FirstOrDefault();
        if (VmList.SelectedItem != null &&
            VmList.ItemContainerGenerator.ContainerFromItem(VmList.SelectedItem) is ListBoxItem item)
            item.Focus();
        else
            VmList.Focus();
    }

    // ── Selection and inspector ────────────────────────────────────────────
    private List<VmDisplayItem> GetSelectedVms()
    {
        var selected = VmList.SelectedItems.OfType<VmDisplayItem>().ToHashSet();
        // In list order, not click order
        return (_vmView?.OfType<VmDisplayItem>() ?? _vmItems).Where(selected.Contains).ToList();
    }

    private void OnVmSelectionChanged(object sender, SelectionChangedEventArgs e) => UpdateInspector();

    private void UpdateInspector()
    {
        // Save an edit in progress to the VM it was typed for, before the panel moves on
        CommitNote();
        var vms = GetSelectedVms();
        InspectorEmpty.Visibility = vms.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        InspectorPanel.Visibility = vms.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
        if (vms.Count == 0) return;

        var running = vms.Count(v => v.IsRunning);
        var single = vms.Count == 1 ? vms[0] : null;
        InspectorDetails.Visibility = single != null ? Visibility.Visible : Visibility.Collapsed;
        SnapshotsBtn.IsEnabled = single != null;
        RollbackBtn.IsEnabled = single is { SnapCount: > 0 };
        OpenConsoleBtn.IsEnabled = running > 0;

        if (single != null)
        {
            InspectorCaption.Text = "Selected";
            InspectorName.Text = single.Name;
            InspectorOs.Text = single.OsLabel;
            InspectorSep.Text = " · ";
            InspectorState.Text = single.StatusText;
            // A resource reference, so it follows theme changes
            InspectorState.SetResourceReference(TextElement.ForegroundProperty, single.IsRunning ? "ThemeGreen" : "ThemeOverlay1");
            OpenConsoleText.Text = "Open SPICE console";
            DetailId.Text = single.VmId.ToString();
            DetailIp.Text = single.IpOrDash;
            DetailNode.Text = single.Node;
            DetailPool.Text = single.PoolOrDash;
            NotesBox.Text = single.Notes;
            NotesBox.Tag = single;
        }
        else
        {
            InspectorCaption.Text = "Selection";
            InspectorName.Text = $"{vms.Count} VMs";
            InspectorOs.Text = $"{running} running";
            InspectorSep.Text = " · ";
            InspectorState.Text = $"{vms.Count - running} stopped";
            InspectorState.SetResourceReference(TextElement.ForegroundProperty, "ThemeSubtext0");
            OpenConsoleText.Text = running == 1 ? "Open 1 console" : $"Open {running} consoles";
            NotesBox.Tag = null;
        }
    }

    private void OnVmDoubleClick(object sender, MouseButtonEventArgs e)
    {
        // Only a double-click on a row itself, not on its buttons or the empty space below
        if (e.OriginalSource is not DependencyObject src ||
            ItemsControl.ContainerFromElement(VmList, src) is not ListBoxItem { DataContext: VmDisplayItem vm } ||
            FindParent<ButtonBase>(src) != null)
            return;
        _ = LaunchAsync([vm]);
    }

    private static T? FindParent<T>(DependencyObject child) where T : DependencyObject
    {
        for (var node = child; node != null; node = VisualTreeHelper.GetParent(node))
            if (node is T t) return t;
        return null;
    }

    private void OnRowConnect(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is not VmDisplayItem vm) return;
        VmList.SelectedItem = vm;
        _ = LaunchAsync([vm]);
    }

    private void OnRowStart(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is not VmDisplayItem vm) return;
        VmList.SelectedItem = vm;
        _ = VmActionAsync([vm], "start", null);
    }

    // ── VM Actions ─────────────────────────────────────────────────────────
    // confirmMsg null: act without asking (starting a VM loses nothing)
    private async Task VmActionAsync(List<VmDisplayItem> vms, string action, string? confirmMsg)
    {
        if (vms.Count == 0)
        {
            MessageBox.Show("Select one or more VMs first.", "No Selection",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        if (confirmMsg != null && MessageBox.Show(confirmMsg, "Confirm", MessageBoxButton.YesNo,
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

        StatusLabel.Text = vms.Count == 1
            ? $"{action} sent to {vms[0].Name}. Refreshing..."
            : $"{action} sent to {vms.Count} VMs. Refreshing...";
        await Task.Delay(3000);
        await RefreshVmsAsync();
    }

    private static string Names(List<VmDisplayItem> vms) =>
        vms.Count == 1 ? vms[0].Name : $"{vms.Count} VMs";

    private void OnStartVm(object sender, RoutedEventArgs e)
        => _ = VmActionAsync(GetSelectedVms(), "start", null);

    private void OnShutdownVm(object sender, RoutedEventArgs e)
    {
        var vms = GetSelectedVms();
        _ = VmActionAsync(vms, "shutdown", $"Send ACPI shutdown to {Names(vms)}?");
    }

    private void OnRebootVm(object sender, RoutedEventArgs e)
    {
        var vms = GetSelectedVms();
        _ = VmActionAsync(vms, "reboot", $"Reboot {Names(vms)}?");
    }

    private void OnForceStopVm(object sender, RoutedEventArgs e)
    {
        var vms = GetSelectedVms();
        _ = VmActionAsync(vms, "stop", $"Force stop {Names(vms)}?\nUnsaved data will be lost.");
    }

    // ── SPICE Launch ───────────────────────────────────────────────────────
    private void OnLaunchSpice(object sender, RoutedEventArgs e) => _ = LaunchAsync(GetSelectedVms());

    private async Task LaunchAsync(List<VmDisplayItem> vms)
    {
        if (vms.Count == 0)
        {
            MessageBox.Show("Select a VM to launch.", "No Selection",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        var running = vms.Where(v => v.IsRunning).ToList();
        if (running.Count == 0)
        {
            StatusLabel.Text = vms.Count == 1
                ? $"{vms[0].Name} is not running. Start it first (S)."
                : "None of the selected VMs are running.";
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

        foreach (var vm in running)
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
                var val = prop.Value.ValueKind == JsonValueKind.Number
                    ? prop.Value.GetRawText()
                    : prop.Value.GetString() ?? "";
                vvContent += $"{key}={val}\n";
            }
            vvContent += "delete-this-file=1\n";

            var vvPath = ViewerService.WriteVvFile(vvContent);

            ViewerService.LaunchSpice(viewer, vvPath);
            StatusLabel.Text = $"Launched SPICE session for {vm.Name}";
        }
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

    // ── Settings menu ──────────────────────────────────────────────────────
    private void OnOpenSettings(object sender, RoutedEventArgs e)
    {
        var hasCluster = _selectedClusterIdx >= 0 && _selectedClusterIdx < _config.Clusters.Count;
        var clusterName = hasCluster ? _config.Clusters[_selectedClusterIdx].Name : "cluster";
        ShowMenu(SettingsBtn, PlacementMode.Top,
        [
            new($"Edit {clusterName}…", EditCluster, hasCluster),
            new($"Remove {clusterName}…", RemoveCluster, hasCluster),
            null,
            new("Import clusters…", ImportConfig),
            new("Export clusters…", ExportConfig),
            null,
            new(DebugLogger.Enabled ? "Debug log: on" : "Debug log: off", ToggleDebugLog),
            new("Open debug log", OpenLogFile, DebugLogger.Enabled),
            new("Check prerequisites", CheckPrereqs),
            new("Create Start Menu shortcut", CreateShortcut),
            null,
            new("GitHub", () => OpenUrl("https://github.com/darthrater78/proxmoxspicemanager")),
            new($"Release notes (v{AppVersion})", () => OpenUrl($"https://github.com/darthrater78/proxmoxspicemanager/releases/tag/v{AppVersion}")),
        ]);
    }

    private record MenuEntry(string Label, Action Run, bool Enabled = true);

    // A themed popup menu of flat buttons; null entries are separators
    private void ShowMenu(UIElement target, PlacementMode placement, IEnumerable<MenuEntry?> entries)
    {
        var popup = new Popup
        {
            PlacementTarget = target,
            Placement = placement,
            StaysOpen = false,
            AllowsTransparency = true,
            PopupAnimation = PopupAnimation.Fade,
        };
        var panel = new StackPanel { MinWidth = 220 };
        foreach (var entry in entries)
        {
            if (entry == null)
            {
                panel.Children.Add(new Border
                {
                    Height = 1,
                    Margin = new Thickness(4, 5, 4, 5),
                    Background = (Brush)FindResource("ThemeSurface1"),
                });
                continue;
            }
            var button = new Button
            {
                Style = (Style)FindResource("NavButton"),
                Content = new TextBlock { Text = entry.Label },
                IsEnabled = entry.Enabled,
            };
            button.Click += (_, _) =>
            {
                popup.IsOpen = false;
                entry.Run();
            };
            panel.Children.Add(button);
        }
        popup.Child = new Border
        {
            Style = (Style)FindResource("PopupCard"),
            Padding = new Thickness(6),
            Child = panel,
        };
        popup.IsOpen = true;
    }

    private static void OpenUrl(string url)
        => Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });

    // ── Import / Export ────────────────────────────────────────────────────
    private void ImportConfig()
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

    private void ExportConfig()
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

    // ── Debug Logging ─────────────────────────────────────────────────────
    private void ToggleDebugLog()
    {
        bool newState = !DebugLogger.Enabled;
        DebugLogger.SetEnabled(newState);
        _config.DebugLogging = newState;
        SaveConfig();
        StatusLabel.Text = newState
            ? $"Debug logging enabled — {DebugLogger.LogFilePath}"
            : "Debug logging disabled";
    }

    private void OpenLogFile()
    {
        var path = DebugLogger.LogFilePath;
        if (File.Exists(path))
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        else
            MessageBox.Show("No log file found yet. Trigger a refresh to generate log entries.",
                "No Log", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    private void CheckPrereqs()
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

    private void OnNotesBoxCommit(object sender, KeyboardFocusChangedEventArgs e) => CommitNote();

    private void OnNotesBoxKey(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            CommitNote();
            FocusList();
            e.Handled = true;
        }
        else if (e.Key == Key.Escape)
        {
            if (NotesBox.Tag is VmDisplayItem vm) NotesBox.Text = vm.Notes;
            FocusList();
            e.Handled = true;
        }
    }

    private void CommitNote()
    {
        if (NotesBox.Tag is not VmDisplayItem vm) return;
        var text = NotesBox.Text.Trim();
        if (vm.Notes == text) return;
        vm.Notes = text;
        SaveVmNote(vm);
    }

    private void OnNotesMenu(object sender, RoutedEventArgs e)
    {
        var entries = new List<MenuEntry?>();
        foreach (var option in _config.NoteOptions ?? [])
            entries.Add(new(option, () => SetNote(option)));
        if (entries.Count > 0) entries.Add(null);
        entries.Add(new("Clear note", () => SetNote(""), NotesBox.Text.Length > 0));
        entries.Add(new("Edit saved notes…", ManageNotes));
        ShowMenu(NotesMenuBtn, PlacementMode.Bottom, entries);
    }

    private void SetNote(string text)
    {
        NotesBox.Text = text;
        CommitNote();
    }

    private void ManageNotes()
    {
        _config.NoteOptions ??= [];
        var dlg = new Dialogs.ManageNotesDialog(_config.NoteOptions) { Owner = this };
        if (dlg.ShowDialog() == true)
        {
            _config.NoteOptions = dlg.GetOptions();
            SaveConfig();
        }
    }

    private void CreateShortcut()
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
                FileName = Path.Combine(Environment.SystemDirectory,
                    "WindowsPowerShell", "v1.0", "powershell.exe"),
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
