using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows;
using System.Windows.Media;

namespace ProxmoxSpiceManager.Models;

public class VmDisplayItem : INotifyPropertyChanged
{
    private bool _isChecked;

    public int VmId { get; set; }
    public string Name { get; set; } = "";
    public string Node { get; set; } = "";
    public string Pool { get; set; } = "";
    public int SnapCount { get; set; }
    public string Status { get; set; } = "";
    public string IpAddress { get; set; } = "";
    private string _notes = "";
    public string Notes
    {
        get => _notes;
        set { _notes = value; OnPropertyChanged(); }
    }

    public bool IsChecked
    {
        get => _isChecked;
        set { _isChecked = value; OnPropertyChanged(); }
    }

    public bool IsRunning => Status.Equals("running", StringComparison.OrdinalIgnoreCase);

    public Brush StatusForeground
    {
        get
        {
            if (IsRunning) return (Brush)Application.Current.Resources["ThemeGreen"];
            return (Brush)Application.Current.Resources["ThemeOverlay0"];
        }
    }

    public Brush StatusBackground
    {
        get
        {
            var theme = Services.ThemeManager.Current;
            if (IsRunning)
            {
                var c = theme.Green;
                return new SolidColorBrush(Color.FromArgb(30, c.R, c.G, c.B));
            }
            var s = theme.Surface1;
            return new SolidColorBrush(Color.FromArgb(80, s.R, s.G, s.B));
        }
    }

    public FontWeight StatusFontWeight => IsRunning ? FontWeights.Bold : FontWeights.Normal;

    public Brush RowForeground => IsRunning
        ? (Brush)Application.Current.Resources["ThemeText"]
        : (Brush)Application.Current.Resources["ThemeOverlay0"];

    public Brush NameForeground => IsRunning
        ? (Brush)Application.Current.Resources["ThemeBlue"]
        : (Brush)Application.Current.Resources["ThemeOverlay0"];

    public event PropertyChangedEventHandler? PropertyChanged;
    private void OnPropertyChanged([CallerMemberName] string? name = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}
