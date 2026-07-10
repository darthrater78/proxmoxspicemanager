using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Input;

namespace ProxmoxSpiceManager.Dialogs;

public partial class ManageNotesDialog : Window
{
    public ObservableCollection<string> Options { get; }

    public ManageNotesDialog(List<string> noteOptions)
    {
        InitializeComponent();
        Options = new ObservableCollection<string>(noteOptions);
        OptionsList.ItemsSource = Options;
    }

    public List<string> GetOptions() => Options.ToList();

    private void OnAdd(object sender, RoutedEventArgs e)
    {
        var text = NewOptionBox.Text.Trim();
        if (string.IsNullOrEmpty(text)) return;
        if (!Options.Contains(text))
            Options.Add(text);
        NewOptionBox.Clear();
        NewOptionBox.Focus();
    }

    private void OnNewOptionKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
            OnAdd(sender, new RoutedEventArgs());
    }

    private void OnDelete(object sender, RoutedEventArgs e)
    {
        if (OptionsList.SelectedItem is string selected)
            Options.Remove(selected);
    }

    private void OnClose(object sender, RoutedEventArgs e)
    {
        DialogResult = true;
        Close();
    }
}
