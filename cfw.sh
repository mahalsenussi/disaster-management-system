export PATH=$PATH:/usr/bin:/usr/local/bin
echo "=== tunnel id + tunnel name (from config + cred json) ==="
grep -nE "^tunnel:|credentials-file|^  tunnel" /etc/cloudflared/config.yml | head; head -c 120 /etc/cloudflared/*.json 2>/dev/null; echo
echo "=== sudo without password for mahmoud? (needed to write /etc/cloudflared/config.yml + restart) ==="
sudo -n true 2>&1 && echo "  -> passwordless sudo: YES" || echo "  -> passwordless sudo: NO"
echo "=== NOPASSWD entries for mahmoud? ==="; sudo -n -l 2>&1 | head -8
echo "=== does the TUNNEL route dns need the tunnel to be named? show name in cred json (it IS the name) ==="
python3 -c "import json,glob;d=json.load(open('/etc/cloudflared/'+glob.glob('/etc/cloudflared/*.json')[0].split('/')[-1]));print('  account:',d.get('AccountTag'),' tunnel_id:',d.get('TunnelID'))" 2>/dev/null
