using System.Windows;

namespace ProxmoxSpiceManager.Dialogs;

public partial class CreateSnapshotDialog : Window
{
    public string? SnapshotName { get; private set; }
    public string? Description { get; private set; }
    public bool IncludeRam { get; private set; }

    public CreateSnapshotDialog()
    {
        InitializeComponent();
        Loaded += (_, _) => NameBox.Focus();
    }

    private void OnCreate(object sender, RoutedEventArgs e)
    {
        var name = NameBox.Text.Trim();
        if (string.IsNullOrEmpty(name))
        {
            MessageBox.Show("Enter a snapshot name.", "Missing Name",
                MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }

        SnapshotName = name;
        Description = DescBox.Text.Trim();
        IncludeRam = RamCheck.IsChecked == true;
        DialogResult = true;
    }
}
