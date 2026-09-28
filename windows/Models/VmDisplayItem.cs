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

    private string _ipAddress = "";
    public string IpAddress
    {
        get => _ipAddress;
        set { _ipAddress = value; OnPropertyChanged(); OnPropertyChanged(nameof(IpOrDash)); }
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
            OnPropertyChanged(nameof(Detail));
        }
    }

    public bool IsRunning => Status.Equals("running", StringComparison.OrdinalIgnoreCase);
    public string StatusText => Status.Length > 0
        ? CultureInfo.CurrentCulture.TextInfo.ToTitleCase(Status)
        : "Unknown";
    public string IpOrDash => IpAddress.Length > 0 ? IpAddress : "—";
    public bool HasNotes => Notes.Length > 0;
    public bool HasPool => Pool.Length > 0;
    public string PoolOrDash => HasPool ? Pool : "—";

    // Second line of a row: "101 · desktops · Daily driver"
    public string Detail => string.Join(" · ",
        new[] { VmId.ToString(), Pool, Notes }.Where(s => s.Length > 0));

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
