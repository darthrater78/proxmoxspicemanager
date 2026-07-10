using System.Windows;
using System.Windows.Media;

namespace ProxmoxSpiceManager.Models;

public class ClusterListItem
{
    public string Name { get; set; } = "";
    public int Index { get; set; }
    public bool IsSelected { get; set; }
    public bool? Online { get; set; }
    public int? VmCount { get; set; }

    public string VmCountText => VmCount?.ToString() ?? "";
    public Visibility VmCountVisibility => VmCount.HasValue ? Visibility.Visible : Visibility.Collapsed;

    public Brush StatusColor
    {
        get
        {
            if (Online == true) return (Brush)Application.Current.Resources["ThemeGreen"];
            if (Online == false) return (Brush)Application.Current.Resources["ThemeOverlay0"];
            return (Brush)Application.Current.Resources["ThemeSurface2"];
        }
    }

    public Brush NameColor => IsSelected
        ? (Brush)Application.Current.Resources["ThemeBlue"]
        : (Brush)Application.Current.Resources["ThemeText"];
}
