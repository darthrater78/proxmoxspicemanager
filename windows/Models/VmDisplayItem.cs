using System.ComponentModel;
using System.Globalization;
using System.Runtime.CompilerServices;

namespace ProxmoxSpiceManager.Models;

public class VmDisplayItem : INotifyPropertyChanged
{
    public int VmId { get; set; }
    public string Name { get; set; } = "";
    public string Node { get; set; } = "";
    public string Pool { get; set; } = "";
    public int SnapCount { get; set; }
    public string Status { get; set; } = "";
    public bool HasAgent { get; set; }
    // Proxmox "ostype" from the VM config: win11, win10, l26, ...
    public string OsType { get; set; } = "";

    // Every address the guest agent reports, with the adapter it's live on
    private IReadOnlyList<(string Adapter, string Ip)> _ips = [];
    public IReadOnlyList<(string Adapter, string Ip)> Ips
    {
        get => _ips;
        set { _ips = value; RefreshAddress(); }
    }

    // Why there's no address: "", "no agent", "agent error"
    private string _ipNote = "";
    public string IpNote
    {
        get => _ipNote;
        set { _ipNote = value; RefreshAddress(); }
    }

    // Set from the "show_ipv6" setting; IPv6 addresses are hidden unless it's on
    public static bool ShowIpv6 { get; set; }
    public IEnumerable<(string Adapter, string Ip)> ShownIps =>
        Ips.Where(a => ShowIpv6 || !a.Ip.Contains(':'));

    // First address, or why there is none; what the list sorts and searches by
    public string IpAddress => ShownIps.Select(a => a.Ip).FirstOrDefault() ?? IpNote;

    // The list cell's input: every shown address, or the one reason there is none
    public IReadOnlyList<string> AddressParts => ShownIps.Any()
        ? ShownIps.Select(a => a.Ip).ToList()
        : [IpNote.Length > 0 ? IpNote : "—"];

    public void RefreshAddress()
    {
        OnPropertyChanged(nameof(IpAddress));
        OnPropertyChanged(nameof(AddressParts));
    }

    private string _notes = "";
    public string Notes
    {
        get => _notes;
        set
        {
            _notes = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(HasNotes));
        }
    }

    public bool IsRunning => Status.Equals("running", StringComparison.OrdinalIgnoreCase);
    public string StatusText => Status.Length > 0
        ? CultureInfo.CurrentCulture.TextInfo.ToTitleCase(Status)
        : "Unknown";

    public bool HasNotes => Notes.Length > 0;
    public bool HasPool => Pool.Length > 0;
    public string PoolOrDash => HasPool ? Pool : "—";

    // Set when the list isn't grouped by node, so each row says where it runs
    public static bool ShowNode { get; set; }

    // Second line of a row: "101 · desktops", led by the node when ungrouped
    public string Detail => string.Join(" · ",
        new[] { ShowNode ? Node : "", VmId.ToString(), Pool }.Where(s => s.Length > 0));

    public void RefreshDetail() => OnPropertyChanged(nameof(Detail));

    public bool IsWindows => OsType.StartsWith('w');
    public string OsBadge => OsType switch
    {
        "" => "VM",
        _ when IsWindows => "WIN",
        "l24" or "l26" => "LNX",
        "solaris" => "SOL",
        _ => "VM",
    };
    public string OsLabel => OsType switch
    {
        "win11" => "Windows 11",
        "win10" => "Windows 10",
        "win8" => "Windows 8",
        "win7" => "Windows 7",
        "w2k8" => "Windows Server 2008",
        "w2k3" => "Windows Server 2003",
        "w2k" => "Windows 2000",
        "wvista" => "Windows Vista",
        "wxp" => "Windows XP",
        "l24" or "l26" => "Linux",
        "solaris" => "Solaris",
        "other" => "Other OS",
        "" => "Unknown OS",
        _ => OsType,
    };

    public event PropertyChangedEventHandler? PropertyChanged;
    private void OnPropertyChanged([CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
