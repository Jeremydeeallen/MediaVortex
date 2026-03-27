# Mac Setup Notes

## To-Do: Add Mac to Prometheus monitoring

### Requirements:
1. Install node_exporter on Mac
2. Configure it to run on startup
3. Add Mac to Prometheus config

### Installation Commands (run on Mac):

```bash
# Download node_exporter for macOS
curl -LO https://github.com/prometheus/node_exporter/releases/download/v1.8.2/node_exporter-1.8.2.darwin-amd64.tar.gz

# Extract
tar -xzf node_exporter-1.8.2.darwin-amd64.tar.gz
sudo mv node_exporter-1.8.2.darwin-amd64/node_exporter /usr/local/bin/

# Create LaunchDaemon plist for auto-start
sudo bash -c 'cat > /Library/LaunchDaemons/io.prometheus.node_exporter.plist' << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>io.prometheus.node_exporter</string>
    <key>ProgramArguments</key>
    <array>
      <string>/usr/local/bin/node_exporter</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/node_exporter.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/node_exporter.err</string>
  </dict>
</plist>
EOF

# Load and start the service
sudo launchctl load /Library/LaunchDaemons/io.prometheus.node_exporter.plist
sudo launchctl start io.prometheus.node_exporter

# Verify it's running
curl http://localhost:9100/metrics | head -10
```

### After Installation:

1. Get Mac's IP address: `ipconfig getifaddr en0`
2. SSH to Prometheus server: `ssh adroit@10.0.0.239`
3. Edit config: `nano /home/adroit/SphinxTeslaMate/prometheus.yml`
4. Add to 'node' job under static_configs:
   ```yaml
   - targets: ['<MAC_IP>:9100']
     labels:
       instance_name: '<mac-hostname>'
       role: 'ai-workstation'
   ```
5. Restart Prometheus: `docker restart sphinxteslamate-prometheus-1`
6. Verify: `curl -s 'http://localhost:9090/api/v1/targets' | grep <MAC_IP>`

### Notes:
- Mac uses node_exporter (same as Linux), not windows_exporter
- Default port: 9100
- Role label: 'ai-workstation' (to match I9-2024 and ai-dev)
