using System.Windows.Media;

namespace ProxmoxSpiceManager.Models;

public class Theme
{
    public string Name { get; set; } = "";
    public Color Base { get; set; }
    public Color Mantle { get; set; }
    public Color Crust { get; set; }
    public Color Surface0 { get; set; }
    public Color Surface1 { get; set; }
    public Color Surface2 { get; set; }
    public Color Overlay0 { get; set; }
    public Color Overlay1 { get; set; }
    public Color Text { get; set; }
    public Color Subtext0 { get; set; }
    public Color Subtext1 { get; set; }
    public Color Blue { get; set; }
    public Color Sapphire { get; set; }
    public Color Green { get; set; }
    public Color Teal { get; set; }
    public Color Yellow { get; set; }
    public Color Peach { get; set; }
    public Color Red { get; set; }
    public Color Mauve { get; set; }
    public Color Lavender { get; set; }
}

public static class Themes
{
    static Color H(string hex) => (Color)ColorConverter.ConvertFromString(hex);

    public static Dictionary<string, Theme> All { get; } = new()
    {
        ["Catppuccin Mocha"] = new()
        {
            Name = "Catppuccin Mocha",
            Base = H("#1e1e2e"), Mantle = H("#181825"), Crust = H("#11111b"),
            Surface0 = H("#313244"), Surface1 = H("#45475a"), Surface2 = H("#585b70"),
            Overlay0 = H("#6c7086"), Overlay1 = H("#7f849c"),
            Text = H("#cdd6f4"), Subtext0 = H("#a6adc8"), Subtext1 = H("#bac2de"),
            Blue = H("#89b4fa"), Sapphire = H("#74c7ec"), Green = H("#a6e3a1"),
            Teal = H("#94e2d5"), Yellow = H("#f9e2af"), Peach = H("#fab387"),
            Red = H("#f38ba8"), Mauve = H("#cba6f7"), Lavender = H("#b4befe"),
        },
        ["Catppuccin Latte"] = new()
        {
            Name = "Catppuccin Latte",
            Base = H("#eff1f5"), Mantle = H("#e6e9ef"), Crust = H("#dce0e8"),
            Surface0 = H("#ccd0da"), Surface1 = H("#bcc0cc"), Surface2 = H("#acb0be"),
            Overlay0 = H("#9ca0b0"), Overlay1 = H("#8c8fa1"),
            Text = H("#4c4f69"), Subtext0 = H("#6c6f85"), Subtext1 = H("#5c5f77"),
            Blue = H("#1e66f5"), Sapphire = H("#209fb5"), Green = H("#40a02b"),
            Teal = H("#179299"), Yellow = H("#df8e1d"), Peach = H("#fe640b"),
            Red = H("#d20f39"), Mauve = H("#8839ef"), Lavender = H("#7287fd"),
        },
        ["Nord"] = new()
        {
            Name = "Nord",
            Base = H("#2e3440"), Mantle = H("#292e39"), Crust = H("#242933"),
            Surface0 = H("#3b4252"), Surface1 = H("#434c5e"), Surface2 = H("#4c566a"),
            Overlay0 = H("#616e88"), Overlay1 = H("#6e7a94"),
            Text = H("#eceff4"), Subtext0 = H("#d8dee9"), Subtext1 = H("#e5e9f0"),
            Blue = H("#88c0d0"), Sapphire = H("#81a1c1"), Green = H("#a3be8c"),
            Teal = H("#8fbcbb"), Yellow = H("#ebcb8b"), Peach = H("#d08770"),
            Red = H("#bf616a"), Mauve = H("#b48ead"), Lavender = H("#81a1c1"),
        },
        ["Dracula"] = new()
        {
            Name = "Dracula",
            Base = H("#282a36"), Mantle = H("#21222c"), Crust = H("#191a21"),
            Surface0 = H("#343746"), Surface1 = H("#3e4157"), Surface2 = H("#484b68"),
            Overlay0 = H("#6272a4"), Overlay1 = H("#7082b4"),
            Text = H("#f8f8f2"), Subtext0 = H("#d0d0d0"), Subtext1 = H("#e0e0e0"),
            Blue = H("#8be9fd"), Sapphire = H("#66d9ef"), Green = H("#50fa7b"),
            Teal = H("#50fa7b"), Yellow = H("#f1fa8c"), Peach = H("#ffb86c"),
            Red = H("#ff5555"), Mauve = H("#bd93f9"), Lavender = H("#bd93f9"),
        },
        ["OLED Dark"] = new()
        {
            Name = "OLED Dark",
            Base = H("#000000"), Mantle = H("#0a0a0a"), Crust = H("#050505"),
            Surface0 = H("#1a1a1a"), Surface1 = H("#262626"), Surface2 = H("#333333"),
            Overlay0 = H("#555555"), Overlay1 = H("#666666"),
            Text = H("#e0e0e0"), Subtext0 = H("#aaaaaa"), Subtext1 = H("#c0c0c0"),
            Blue = H("#5ea6ff"), Sapphire = H("#4dc9f6"), Green = H("#67d98a"),
            Teal = H("#4dd8b0"), Yellow = H("#f0c060"), Peach = H("#e89050"),
            Red = H("#f06070"), Mauve = H("#b080e0"), Lavender = H("#9090e0"),
        },
    };
}
