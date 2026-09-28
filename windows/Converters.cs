using System.Collections;
using System.Globalization;
using System.Windows.Data;
using ProxmoxSpiceManager.Models;

namespace ProxmoxSpiceManager;

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
