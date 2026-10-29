#!/usr/bin/env bash
# Start a TURN relay (coturn) on the host, so that browsers on a network that
# blocks UDP get WebRTC over TCP. It writes runtime/turn/turnserver.conf and
# runtime/turn/ice.json, then runs turnserver in the foreground.
#   tools/run-turn.sh [--lan-ip IP] [--tailnet-host NAME | --no-tailnet]
#                     [--port 3478] [--tls-port 5349 | --tailnet-tcp-port PORT] [--tailnet-only]
#                     [--new-password] [--docker] [--config-only]
# Addresses that you do not give are found on the host. The relay relays only
# to the host's own LAN address. --tailnet-tcp-port offers the tailnet relay
# as plain TCP, for tailnet ACLs that allow only some ports. --tailnet-only
# gives browsers the tailnet relay only. --docker runs the official coturn
# image instead of a local turnserver.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
root=$PWD
dir=runtime/turn
lan_ip= tailnet_host= tailnet=1 port=3478 tls_port=5349 tcp_port= tailnet_only= new_password= config_only= docker=
image=coturn/coturn:4.18.0

fail() { echo "run-turn.sh: $*" >&2; exit 2; }
value() { [[ $# -ge 2 && -n $2 ]] || fail "$1 needs a value"; }
while [[ $# -gt 0 ]]; do
  case $1 in
    --lan-ip) value "$@"; lan_ip=$2; shift 2 ;;
    --tailnet-host) value "$@"; tailnet_host=$2; shift 2 ;;
    --no-tailnet) tailnet=; shift ;;
    --port) value "$@"; port=$2; shift 2 ;;
    --tls-port) value "$@"; tls_port=$2; shift 2 ;;
    --tailnet-tcp-port) value "$@"; tcp_port=$2; shift 2 ;;
    --tailnet-only) tailnet_only=1; shift ;;
    --new-password) new_password=1; shift ;;
    --config-only) config_only=1; shift ;;
    --docker) docker=1; shift ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fail "unknown option $1" ;;
  esac
done

ipv4() {
  [[ $1 =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
  local part
  for part in "${BASH_REMATCH[@]:1}"; do (( 10#$part <= 255 )) || return 1; done
}
valid_port() { [[ $1 =~ ^[0-9]{1,5}$ ]] && (( 10#$1 >= 1 && 10#$1 <= 65535 )); }
python() { if [[ -x $root/.venv/bin/python ]]; then "$root/.venv/bin/python" "$@"; else python3 "$@"; fi; }
tailscale_cli() {
  if command -v tailscale >/dev/null; then tailscale "$@"
  elif [[ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]]; then
    /Applications/Tailscale.app/Contents/MacOS/Tailscale "$@"
  else return 1; fi
}

if [[ -z $lan_ip ]]; then
  if [[ $(uname) == Darwin ]]; then
    lan_ip=$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || true)
  else
    lan_ip=$(ip -4 route get 192.0.2.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' || true)
    [[ -n $lan_ip ]] || lan_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
  fi
  [[ -n $lan_ip ]] || fail "no LAN address found. Give it with --lan-ip"
fi
if [[ -n $tailnet ]]; then
  [[ -n $tailnet_host ]] || tailnet_host=$(tailscale_cli status --json 2>/dev/null |
    python -c 'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)
  if [[ -z $tailnet_host ]]; then
    echo "No tailnet found. The relay is for the LAN only. Use --tailnet-host to add it."
    tailnet=
  fi
fi
[[ -z $tailnet_only || -n $tailnet ]] || fail "--tailnet-only needs a tailnet"
ipv4 "$lan_ip" || fail "the LAN address is not an IPv4 address: $lan_ip"
valid_port "$port" || fail "--port must be from 1 to 65535"
valid_port "$tls_port" || fail "--tls-port must be from 1 to 65535"
[[ -z $tcp_port ]] || valid_port "$tcp_port" || fail "--tailnet-tcp-port must be from 1 to 65535"
if [[ -n $tailnet ]]; then
  [[ $tailnet_host =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || fail "the tailnet host name is not valid: $tailnet_host"
fi

# Only this user can read the password and the files that contain it.
umask 077
mkdir -p "$dir"
chmod 700 "$dir"
if [[ -n $new_password || ! -s $dir/password ]]; then
  od -An -tx1 -N24 /dev/urandom | tr -d ' \n' > "$dir/password.new"
  echo >> "$dir/password.new"
  mv "$dir/password.new" "$dir/password"
fi
password=$(tr -d ' \n' < "$dir/password")
[[ $password =~ ^[A-Za-z0-9]+$ ]] || fail "$dir/password must contain only letters and digits"

# Docker Desktop (macOS, Windows) has no real host network. There, coturn
# listens and relays on the container address, and Docker publishes the port.
bridge=
[[ -n $docker && $(uname) != Linux ]] && bridge=1
if [[ -n $bridge ]]; then
  listen="listening-port=3478"
else
  listen="listening-ip=$lan_ip
listening-ip=127.0.0.1
listening-port=$port
relay-ip=127.0.0.1"
fi
if [[ -n $docker ]]; then
  state=/tmp
else
  state=$root/$dir
fi

urls=()
[[ -n $tailnet_only ]] || urls+=("\"turn:$lan_ip:$port?transport=tcp\"")
if [[ -n $tailnet && -n $tcp_port ]]; then
  # tailscale serve sends the TCP stream to 127.0.0.1. WireGuard encrypts it on the tailnet.
  urls+=("\"turn:$tailnet_host:$tcp_port?transport=tcp\"")
  serve="tailscale serve --bg --tcp $tcp_port tcp://127.0.0.1:$port"
elif [[ -n $tailnet ]]; then
  # tailscale serve terminates TLS on the tailnet and sends plain TCP to 127.0.0.1.
  urls+=("\"turns:$tailnet_host:$tls_port?transport=tcp\"")
  serve="tailscale serve --bg --tls-terminated-tcp $tls_port tcp://127.0.0.1:$port"
fi

cat > "$dir/turnserver.conf.new" <<EOF
# Made by tools/run-turn.sh. Do not edit: the script writes it again.
$listen
realm=sofa-link
lt-cred-mech
user=sofa:$password
fingerprint
# Clients use TCP only. Tailscale gives TLS on the tailnet.
no-udp
no-tls
no-tcp-relay
# Relay only to the host. coturn always refuses loopback peers.
# The host offers its LAN address, so the relay needs no other peer. Do not
# allow the tailnet address: on macOS, coturn cannot send from 127.0.0.1 to
# it, and the failed send closes the browser's allocation.
allowed-peer-ip=$lan_ip
denied-peer-ip=0.0.0.0-255.255.255.255
denied-peer-ip=::-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff
no-multicast-peers
# Twelve browsers with two relay addresses each.
total-quota=24
no-cli
no-software-attribute
pidfile=$state/turnserver.pid
userdb=$state/turndb
log-file=stdout
simple-log
EOF
cat > "$dir/ice.json.new" <<EOF
[
  {
    "urls": [$(IFS=,; echo "${urls[*]}" | sed 's/,/, /g')],
    "username": "sofa",
    "credential": "$password"
  }
]
EOF
mv "$dir/turnserver.conf.new" "$dir/turnserver.conf"
mv "$dir/ice.json.new" "$dir/ice.json"

[[ -n $tailnet_only ]] || echo "Relay: turn:$lan_ip:$port (TCP)"
echo "Start the host with: --ice-config $root/$dir/ice.json"
if [[ -n $tailnet ]]; then
  echo "Relay on the tailnet: ${urls[${#urls[@]}-1]//\"/}. Add the serve entry once:"
  echo "  $serve"
fi
[[ -z $config_only ]] || exit 0

if [[ -n $docker ]]; then
  command -v docker >/dev/null || fail "docker is not installed"
  # The config is read-only in the container. Only the config file contains
  # the password. The container user is this user, so it can read the file.
  args=(--rm --init --name sofa-link-turn "--user=$(id -u):$(id -g)"
        --volume "$root/$dir/turnserver.conf:/etc/coturn/turnserver.conf:ro")
  if [[ -n $bridge ]]; then
    args+=("--publish=$lan_ip:$port:3478/tcp" "--publish=127.0.0.1:$port:3478/tcp")
  else
    args+=(--network=host)
  fi
  # This replaces the default arguments of the image, which find a public IP address.
  exec docker run "${args[@]}" "$image" -c /etc/coturn/turnserver.conf
fi

turnserver=${TURNSERVER:-turnserver}
command -v "$turnserver" >/dev/null ||
  fail "turnserver is not installed. Install coturn: 'brew install coturn' (macOS) or 'sudo apt install coturn' (Linux)"
exec "$turnserver" -c "$root/$dir/turnserver.conf"
