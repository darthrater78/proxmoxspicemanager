using System.Windows;
using System.Windows.Media;
using ProxmoxSpiceManager.Models;

namespace ProxmoxSpiceManager.Services;

public static class ThemeManager
{
    public static Theme Current { get; private set; } = Themes.All["Catppuccin Mocha"];

    public static void Apply(string themeName)
    {
        if (!Themes.All.TryGetValue(themeName, out var theme))
            return;

        Current = theme;

        var res = Application.Current.Resources;
        res["ThemeBase"] = new SolidColorBrush(theme.Base);
        res["ThemeMantle"] = new SolidColorBrush(theme.Mantle);
        res["ThemeCrust"] = new SolidColorBrush(theme.Crust);
        res["ThemeSurface0"] = new SolidColorBrush(theme.Surface0);
        res["ThemeSurface1"] = new SolidColorBrush(theme.Surface1);
        res["ThemeSurface2"] = new SolidColorBrush(theme.Surface2);
        res["ThemeOverlay0"] = new SolidColorBrush(theme.Overlay0);
        res["ThemeOverlay1"] = new SolidColorBrush(theme.Overlay1);
        res["ThemeText"] = new SolidColorBrush(theme.Text);
        res["ThemeSubtext0"] = new SolidColorBrush(theme.Subtext0);
        res["ThemeSubtext1"] = new SolidColorBrush(theme.Subtext1);
        res["ThemeBlue"] = new SolidColorBrush(theme.Blue);
        res["ThemeSapphire"] = new SolidColorBrush(theme.Sapphire);
        res["ThemeGreen"] = new SolidColorBrush(theme.Green);
        res["ThemeTeal"] = new SolidColorBrush(theme.Teal);
        res["ThemeYellow"] = new SolidColorBrush(theme.Yellow);
        res["ThemePeach"] = new SolidColorBrush(theme.Peach);
        res["ThemeRed"] = new SolidColorBrush(theme.Red);
        res["ThemeMauve"] = new SolidColorBrush(theme.Mauve);
        res["ThemeLavender"] = new SolidColorBrush(theme.Lavender);
    }
}
