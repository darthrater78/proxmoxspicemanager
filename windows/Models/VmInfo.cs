namespace ProxmoxSpiceManager.Models;

public class VmInfo
{
    public int VmId { get; set; }
    public string Name { get; set; } = "";
    public string Node { get; set; } = "";
    public string Pool { get; set; } = "";
    public string Status { get; set; } = "";
    public int SnapCount { get; set; }
    public string Notes { get; set; } = "";
    public bool IsChecked { get; set; }

    public bool IsRunning => Status.Equals("running", StringComparison.OrdinalIgnoreCase);
}
