using System.Collections;
using System.Globalization;
using System.Windows.Data;
using ProxmoxSpiceManager.Models;

namespace ProxmoxSpiceManager;

// Orders VMs by one of the shared sort keys; node first when the list is grouped
public class VmComparer(string key, bool descending, bool byNodeFirst) : IComparer
{
    public static readonly Dictionary<string, string> Labels = new()
    {
        ["name"] = "Name", ["vmid"] = "ID", ["ip"] = "Address", ["node"] = "Node",
        ["pool"] = "Pool", ["snaps"] = "Snapshots", ["status"] = "Status", ["notes"] = "Notes",
    };

    public int Compare(object? x, object? y)
    {
        if (x is not VmDisplayItem a || y is not VmDisplayItem b) return 0;
        if (byNodeFirst)
        {
            var node = string.Compare(a.Node, b.Node, StringComparison.OrdinalIgnoreCase);
            if (node != 0) return node;
        }
        var result = key switch
        {
            "name" => Text(a.Name, b.Name),
            "ip" => Ip(a.IpAddress).CompareTo(Ip(b.IpAddress)),
            "node" => Text(a.Node, b.Node),
            "pool" => Text(a.Pool, b.Pool),
            "snaps" => a.SnapCount.CompareTo(b.SnapCount),
            "status" => (a.IsRunning ? 0 : 1).CompareTo(b.IsRunning ? 0 : 1) is var r and not 0
                ? r : Text(a.Status, b.Status),
            "notes" => Text(a.Notes, b.Notes),
            _ => a.VmId.CompareTo(b.VmId),
        };
        if (result == 0 && key != "vmid") result = a.VmId.CompareTo(b.VmId);
        return descending ? -result : result;
    }

    // Blanks after values, then case-insensitive
    private static int Text(string a, string b) =>
        (a.Length == 0).CompareTo(b.Length == 0) is var blank and not 0
            ? blank : string.Compare(a, b, StringComparison.OrdinalIgnoreCase);

    // Numeric order, IPv4 before IPv6; "", "no agent" and the like after every address
    private static (int, int, UInt128, string) Ip(string ip)
    {
        if (!System.Net.IPAddress.TryParse(ip, out var addr)) return (1, 0, 0, ip);
        var bytes = new byte[16];
        var raw = addr.GetAddressBytes();
        raw.CopyTo(bytes, 16 - raw.Length);
        return (0, raw.Length, System.Buffers.Binary.BinaryPrimitives.ReadUInt128BigEndian(bytes), "");
    }
}

// A node group's items to "2/3 running"
public class NodeSummaryConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        if (value is not IEnumerable items) return "";
        var vms = items.OfType<VmDisplayItem>().ToList();
        return $"{vms.Count(v => v.IsRunning)}/{vms.Count} running";
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
