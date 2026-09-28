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

    // VM count once loaded, "offline" when the last attempt failed
    public string CountText => Online == false ? "offline" : VmCount?.ToString() ?? "";

    public Brush StatusColor
    {
        get
        {
            if (Online == true) return (Brush)Application.Current.Resources["ThemeGreen"];
            if (Online == false) return (Brush)Application.Current.Resources["ThemeOverlay0"];
            return (Brush)Application.Current.Resources["ThemeSurface2"];
        }
    }
}

// A row of the appearance flyout's theme list
public class ThemeChoice
{
    public string Name { get; init; } = "";
    public Brush Crust { get; init; } = Brushes.Black;
    public Brush Base { get; init; } = Brushes.Black;
    public Brush Surface { get; init; } = Brushes.Gray;
    public Brush Text { get; init; } = Brushes.White;
    public Brush Accent { get; init; } = Brushes.Orange;
    public bool IsSelected { get; init; }
}

// A swatch of the appearance flyout's accent row
public class AccentChoice
{
    public string Name { get; init; } = "";
    public Brush Brush { get; init; } = Brushes.Orange;
    public bool IsSelected { get; init; }
}
