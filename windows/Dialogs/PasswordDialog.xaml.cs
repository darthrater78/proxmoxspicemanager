using System.Windows;

namespace ProxmoxSpiceManager.Dialogs;

public partial class PasswordDialog : Window
{
    public string? Password { get; private set; }

    public PasswordDialog(string username, string host)
    {
        InitializeComponent();
        UserLabel.Text = $"Password for {username}";
        HostLabel.Text = host;
        Loaded += (_, _) => PasswordBox.Focus();
    }

    private void OnConnect(object sender, RoutedEventArgs e)
    {
        Password = PasswordBox.Password;
        DialogResult = true;
    }
}
