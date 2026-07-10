using System.Text.Json;
using System.Windows;
using ProxmoxSpiceManager.Models;
using ProxmoxSpiceManager.Services;

namespace ProxmoxSpiceManager.Dialogs;

public record SnapshotItem(string Name, string Date, string Description);

public partial class SnapshotDialog : Window
{
    private readonly VmDisplayItem _vm;
    private readonly ClusterConfig _cluster;
    private readonly AuthInfo _auth;

    public SnapshotDialog(VmDisplayItem vm, ClusterConfig cluster, AuthInfo auth)
    {
        InitializeComponent();
        _vm = vm;
        _cluster = cluster;
        _auth = auth;

        SnapHeader.Text = $"Snapshots for {vm.Name}";
        Title = $"Snapshots — {vm.Name} (VM {vm.VmId})";

        Loaded += async (_, _) => await LoadSnapshots();
    }

    private async Task LoadSnapshots()
    {
        SnapStatus.Text = "Loading snapshots...";
        SnapGrid.ItemsSource = null;

        var json = await ProxmoxApi.RequestAsync(
            _cluster.Host,
            $"/api2/json/nodes/{_vm.Node}/qemu/{_vm.VmId}/snapshot",
            auth: _auth);

        if (json?.TryGetProperty("data", out var data) != true)
        {
            SnapStatus.Text = "Failed to load snapshots.";
            return;
        }

        var items = data.EnumerateArray()
            .Where(s => s.TryGetProperty("name", out var n) && n.GetString() != "current")
            .OrderByDescending(s => s.TryGetProperty("snaptime", out var t) ? t.GetInt64() : 0)
            .Select(s =>
            {
                var snaptime = s.TryGetProperty("snaptime", out var t) ? t.GetInt64() : 0;
                var date = snaptime > 0
                    ? DateTimeOffset.FromUnixTimeSeconds(snaptime).LocalDateTime.ToString("yyyy-MM-dd  HH:mm:ss")
                    : "—";
                return new SnapshotItem(
                    s.GetProperty("name").GetString() ?? "",
                    date,
                    s.TryGetProperty("description", out var d) ? d.GetString() ?? "" : "");
            })
            .ToList();

        SnapGrid.ItemsSource = items;
        SnapStatus.Text = items.Count > 0 ? $"{items.Count} snapshot(s)" : "No snapshots found.";
    }

    private void OnRefreshSnaps(object sender, RoutedEventArgs e) => _ = LoadSnapshots();

    private async void OnRollback(object sender, RoutedEventArgs e)
    {
        if (SnapGrid.SelectedItem is not SnapshotItem snap)
        {
            MessageBox.Show("Select a snapshot to rollback to.", "No Selection",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        if (MessageBox.Show($"Rollback VM {_vm.VmId} to '{snap.Name}'?\nCurrent state will be lost.",
            "Confirm Rollback", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
            return;

        SnapStatus.Text = $"Rolling back to '{snap.Name}'...";
        var result = await ProxmoxApi.RequestAsync(
            _cluster.Host,
            $"/api2/json/nodes/{_vm.Node}/qemu/{_vm.VmId}/snapshot/{Uri.EscapeDataString(snap.Name)}/rollback",
            "POST", _auth);

        SnapStatus.Text = result != null ? $"Rolled back to '{snap.Name}'" : "Rollback failed";
        await Task.Delay(3000);
        await LoadSnapshots();
    }

    private async void OnDelete(object sender, RoutedEventArgs e)
    {
        if (SnapGrid.SelectedItem is not SnapshotItem snap) return;

        if (MessageBox.Show($"Delete snapshot '{snap.Name}'?\nThis cannot be undone.",
            "Delete Snapshot", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
            return;

        SnapStatus.Text = $"Deleting '{snap.Name}'...";
        await ProxmoxApi.RequestAsync(
            _cluster.Host,
            $"/api2/json/nodes/{_vm.Node}/qemu/{_vm.VmId}/snapshot/{Uri.EscapeDataString(snap.Name)}",
            "DELETE", _auth);

        await Task.Delay(2000);
        await LoadSnapshots();
    }

    private async void OnCreate(object sender, RoutedEventArgs e)
    {
        var dlg = new CreateSnapshotDialog { Owner = this };
        if (dlg.ShowDialog() != true || string.IsNullOrEmpty(dlg.SnapshotName)) return;

        SnapStatus.Text = $"Creating snapshot '{dlg.SnapshotName}'...";

        var endpoint = $"/api2/json/nodes/{_vm.Node}/qemu/{_vm.VmId}/snapshot" +
                       $"?snapname={Uri.EscapeDataString(dlg.SnapshotName)}";
        if (!string.IsNullOrEmpty(dlg.Description))
            endpoint += $"&description={Uri.EscapeDataString(dlg.Description)}";
        if (dlg.IncludeRam)
            endpoint += "&vmstate=1";

        await ProxmoxApi.RequestAsync(_cluster.Host, endpoint, "POST", _auth);
        await Task.Delay(3000);
        await LoadSnapshots();
    }
}
