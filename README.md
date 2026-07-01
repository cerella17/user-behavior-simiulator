# User Behavior Simulator

A comprehensive cross-platform Python tool that simulates realistic human computer usage patterns for testing, research, and automation purposes.

## 🚀 Features

- **🌐 Intelligent Web Browsing** - Visits websites with realistic scrolling and link exploration
- **📺 YouTube Integration** - Watches videos with human-like interaction patterns
- **📝 Dynamic File Operations** - Creates documents using API-generated content
- **🌍 Network File Sharing** - Transfers files across network with IP range support
- **📧 SMTP Email Traffic** - Sends emails with random attachments
- **🔐 SSH Operations** - Executes remote commands with logging
- **📁 FTP Traffic** - Upload/download operations on FTP servers
- **💻 Random App Execution** - Launches and manages applications across platforms
- **⏰ Flexible Scheduling** - Time-based or random task execution
- **🕐 Active Hours Control** - Restricts activity to business hours

## 📦 Installation

### From PyPI

```bash
pip install user-behavior-simulator
```

### From Source

```bash
git clone https://github.com/username/user-behavior-simulator.git
cd user-behavior-simulator
pip install -e .
```

## 🚀 Quick Start

### 1. Create Configuration

```bash
user-behavior-simulator --create-config
```

### 2. Edit Configuration

Edit the generated `config.json` file:

```json
{
  "websites": ["https://example.com"],
  "active_hours": {
    "enabled": true,
    "start_hour": 9,
    "end_hour": 17
  },
  "page_interaction": {
    "scroll_enabled": true
  }
}
```

### 3. Run Simulator

```bash
user-behavior-simulator
```

### Run Only Filesystem Exploration

```bash
user-behavior-simulator --task browse_filesystem
```

## ⚙️ Configuration Examples

### Basic Web Browsing

```json
{
  "websites": ["https://www.reddit.com", "https://news.ycombinator.com"],
  "links_per_website": [3, 7],
  "page_interaction": {
    "scroll_enabled": true,
    "scroll_patterns": ["top_to_bottom", "random_sections"]
  }
}
```

### Network Operations

```json
{
  "ip_range": {
    "enabled": true,
    "start_ip": "192.168.1.100",
    "end_ip": "192.168.1.200"
  },
  "smtp_config": {
    "enabled": true,
    "server": "smtp.gmail.com",
    "recipients": ["test@example.com"]
  }
}
```

### Application Execution

```json
{
  "app_execution": {
    "enabled": true,
    "apps_per_session": [1, 3],
    "windows_apps": [{ "type": "command", "command": "notepad.exe", "name": "Notepad" }]
  }
}
```

## 🖥️ Platform Support

- **Windows** - Full support including system apps and modern applications
- **Linux** - Desktop environments (GNOME, KDE, XFCE) with auto-discovery
- **macOS** - Native application support with .app bundle handling

## 🌐 Network Features

### File Sharing

- Cross-platform network file transfers
- IP range scanning and availability checking
- Retry logic with fallback mechanisms

### Protocol Support

- **HTTP/HTTPS** - Web browsing with realistic interaction
- **FTP** - File upload/download operations
- **SMTP** - Email sending with attachments
- **SSH** - Remote command execution

## 📋 Requirements

- Python 3.6+
- Network connectivity (for some features)
- Platform-specific dependencies:
  - **Windows**: Built-in libraries
  - **Linux**: `python3-tk` for GUI automation
  - **macOS**: Accessibility permissions for automation

```bash
pip install requests pyautogui paramiko
```

## 🔧 Usage

### Command Line

```bash
# Basic usage
user-behavior-simulator

# Custom config
user-behavior-simulator -c my_config.json

# Create default config
user-behavior-simulator --create-config
```

### Python API

```python
from user_behavior_simulator import UserBehaviorSimulator

simulator = UserBehaviorSimulator('config.json')
simulator.start()
```

## 📖 Documentation

- [Configuration Guide](docs/configuration.md)
- [Network Setup](docs/network-setup.md)
- [Application Integration](docs/app-execution.md)
- [Troubleshooting](docs/troubleshooting.md)

## 🛡️ Security

This tool is designed for legitimate testing and research purposes. Please ensure:

- Use only on networks you own or have permission to test
- Configure appropriate firewall rules
- Monitor resource usage and network traffic
- Follow your organization's security policies

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔍 Use Cases

- **Quality Assurance** - Automated testing of applications and websites
- **Network Testing** - Simulate realistic network traffic patterns
- **Performance Testing** - Generate realistic system load
- **Security Research** - Test monitoring and detection systems
- **Automation Research** - Study human-computer interaction patterns

## ⚠️ Disclaimer

This software is provided for educational and testing purposes. Users are responsible for ensuring compliance with applicable laws and regulations. The authors are not responsible for any misuse of this software.

## 🐛 Issue Reporting

Found a bug? Please [create an issue](https://github.com/username/user-behavior-simulator/issues) with:

- Operating system and version
- Python version
- Configuration file (remove sensitive data)
- Error messages and logs

## 📊 Roadmap

- [ ] GUI configuration interface
- [ ] Machine learning-based behavior patterns
- [ ] Additional protocol support (SFTP, IMAP)
- [ ] Browser automation integration
- [ ] Advanced scheduling features
- [ ] Performance analytics dashboard

---

⭐ **Star this repo** if you find it useful!
