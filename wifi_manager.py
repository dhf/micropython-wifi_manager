# Author: Igor Ferreira / D.Friedrich
# License: MIT
# Version: 2.0.0
# Description: WiFi Manager for ESP8266 and ESP32 using MicroPython.
# 05/09/2022: Added utf-8 characters to password field, from 0x20 to 0x7e

import machine
import network
import usocket
import ure
import utime
import os


class WifiManager:

    def __init__(self, ssid='WifiManager', password='wifimanager'):
        self.wlan_sta = network.WLAN(network.STA_IF)
        self.wlan_sta.active(True)
        self.wlan_ap = network.WLAN(network.AP_IF)

        # Avoids simple mistakes with wifi ssid and password lengths, but doesn't check for forbidden or unsupported
        # characters.
        if len(ssid) > 32:
            raise Exception('The SSID cannot be longer than 32 characters.')
        else:
            self.ap_ssid = ssid
        if len(password) < 8:
            raise Exception('The password cannot be less than 8 characters long.')
        else:
            self.ap_password = password

        # Set the access point authentication mode to WPA2-PSK.
        self.ap_authmode = 3

        # The file were the credentials will be stored.
        # There is no encryption, it's just a plain text archive. Be aware of this security problem!
        self.sta_profiles = 'wifi.dat'

        # Prevents the device from automatically trying to connect to the last saved network without first going
        # through the steps defined in the code.
        self.wlan_sta.disconnect()

        # Change to True if you want the device to reboot after configuration.
        # Useful if you're having problems with web server applications after WiFi configuration.
        self.reboot = False

    def connect(self):
        if self.wlan_sta.isconnected():
            return
        profiles = self._read_profiles()
        for ssid, *_ in self.wlan_sta.scan():
            ssid = ssid.decode("utf-8")
            if ssid in profiles:
                password = profiles[ssid]
                if self._wifi_connect(ssid, password):
                    return
        print('Could not connect to any WiFi network. Starting the configuration portal...')
        self._web_server()

    def disconnect(self):
        if self.wlan_sta.isconnected():
            self.wlan_sta.disconnect()

    def is_connected(self):
        return self.wlan_sta.isconnected()

    def get_address(self):
        return self.wlan_sta.ifconfig()

    def delete_profiles(self):
        try:
            if os.path.exists(self.sta_profiles):
                os.remove(self.sta_profiles)
        except OSError:
            print('Error deleting profiles file %s' % self.sta_profiles)

    def _write_profiles(self, profiles):
        lines = []
        for ssid, password in profiles.items():
            lines.append('{0};{1}\n'.format(ssid, password))
        with open(self.sta_profiles, 'w') as myfile:
            myfile.write(''.join(lines))

    def _read_profiles(self):
        try:
            with open(self.sta_profiles) as myfile:
                lines = myfile.readlines()
        except OSError:
            lines = []
            pass
        profiles = {}
        for line in lines:
            ssid, password = line.strip().split(';')
            profiles[ssid] = password
        return profiles

    def _wifi_connect(self, ssid, password):
        print('Trying to connect to:', ssid)
        self.wlan_sta.connect(ssid, password)
        for _ in range(100):
            if self.wlan_sta.isconnected():
                print('\nConnected! Network information:', self.wlan_sta.ifconfig())
                return True
            else:
                print('.', end='')
                utime.sleep_ms(100)
        print('\nConnection failed!')
        self.wlan_sta.disconnect()
        return False

    def _web_server(self):
        self.wlan_ap.active(True)
        self.wlan_ap.config(essid=self.ap_ssid, password=self.ap_password, authmode=self.ap_authmode)
        server_socket = usocket.socket()
        server_socket.close()
        server_socket = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        server_socket.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
        server_socket.bind(('', 80))
        server_socket.listen(1)
        print('Connect to', self.ap_ssid, 'with the password', self.ap_password, 'and access the captive portal at',
              self.wlan_ap.ifconfig()[0])
        while True:
            if self.wlan_sta.isconnected():
                self.wlan_ap.active(False)
                if self.reboot:
                    print('The device will reboot in 5 seconds.')
                    utime.sleep(5)
                    machine.reset()
                return
            self.client, addr = server_socket.accept()
            try:
                self.client.settimeout(5.0)
                self.request = b''
                try:
                    while True:
                        if '\r\n\r\n' in self.request:
                            # Fix for Safari browser
                            self.request += self.client.recv(512)
                            break
                        self.request += self.client.recv(128)
                except OSError:
                    # It's normal to receive timeout errors in this stage, we can safely ignore them.
                    pass
                if self.request:
                    url = ure.search('(?:GET|POST) /(.*?)(?:\\?.*?)? HTTP', self.request).group(1).decode(
                        'utf-8').rstrip('/')
                    if url == '':
                        self._handle_root()
                    elif url == 'configure':
                        self._handle_configure()
                    else:
                        self._handle_not_found()
            except Exception as ex:
                template = "An exception of type {0} occurred. Arguments:\n{1!r}"
                message = template.format(type(ex).__name__, ex.args)
                print('Something went wrong! Reboot and try again.\n%s' % message)
                return
            finally:
                self.client.close()

    def _send_header(self, status_code=200):
        self.client.send("""HTTP/1.1 {0} OK\r\n""".format(status_code))
        self.client.send("""Content-Type: text/html\r\n""")
        self.client.send("""Connection: close\r\n""")
        self.client.send("\r\n")

    def _send_response(self, payload, status_code=200):
        self._send_header(status_code)
        self.client.sendall("""\
            <!DOCTYPE html>
            <html lang="en">
                <head>
                    <title>WiFi Manager</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <link rel="icon" href="data:,">
                    <style>
                        html {{
                            background-color: #eee;
                        }}
                        body {{ 
                            font-family: sans-serif;
                            max-width: 500px;
                            margin: 25px auto;
                            font-size: 1rem;
                        }}
                        #container {{
                            border: outset silver 1px;
                            background-color: white;
                            padding: 25px;
                            margin: 0 0 50px 0;
                            color: #000;
                            font-size: 1rem;
                        }}
                        h1 {{
                            margin-top: 0;
                            text-align: center;
                        }}
                    </style>
                </head>
                <body>
                    {0}
                </body>
            </html>
        """.format(payload))
        self.client.close()

    def _handle_root(self):
        payload = """\
                    <div id="container">
                    <h1>{0}</h1>
                    <form action="/configure" method="post" accept-charset="utf-8">
        """.format(self.ap_ssid)
        all_ssids = (ssid.decode('utf-8') for ssid, *_ in self.wlan_sta.scan())
        unique_ssids = list(set(all_ssids))
        for ssid in sorted(unique_ssids):
            payload += """
                       <div><label><input type="radio" name="ssid" value="{0}" />&nbsp;{0}</label></div>
            """.format(ssid)
        payload += """
                        <p><label for="password">Password:&nbsp;</label><input type="password" id="password" name="password"></p>
                        <p><input type="submit" value="Connect"></p>
                    </form>
                    </div>
                    <p>
                Your ssid and password information will be saved into the file {0}
                in your ESP module for future usage.
                Be careful about security!
            </p>
        """.format(self.sta_profiles)
        self._send_response(payload)

    def _handle_configure(self):
        match = ure.search('ssid=(.*)&password=(.*)', self.request)
        if match:
            ssid = match.group(1).decode('UTF-8').replace('+', ' ')
            password = match.group(2).decode('UTF-8')
            ssid = self._decode_uri(ssid)
            password = self._decode_uri(password)
            if len(ssid) == 0:
                self._send_response("""<p>SSID must be providaded!</p><p>Go back and try again!</p>""", 400)
            elif self._wifi_connect(ssid, password):
                self._send_response(
                    """<p>Successfully connected to</p><h1>{0}</h1><p>IP address: {1}</p>
                    """.format(ssid,
                               self.wlan_sta.ifconfig()[
                                   0]))
                profiles = self._read_profiles()
                profiles[ssid] = password
                self._write_profiles(profiles)
                utime.sleep(5)
            else:
                self._send_response(
                    """<p>Could not connect to</p><h1>{0}</h1><p>Go back and try again!</p>""".format(ssid))
                utime.sleep(5)
        else:
            self._send_response("""<p>Parameters not found!</p>""", 400)
            utime.sleep(5)

    def _handle_not_found(self):
        self._send_response("""<p>Path not found!</p>""", 404)
        utime.sleep(5)

    @staticmethod
    def _decode_uri(uri):
        _uri = uri.split('%')
        if len(_uri[0]) >= 0:
            decoded_uri = ''.join([chr(int(_uri[i + 1][:2], 16)) + _uri[i + 1][2:] for i, _ in enumerate(_uri[1:])])
            decoded_uri = _uri[0] + decoded_uri
        else:
            decoded_uri = ''.join([chr(int(_uri[i][:2], 16)) + _uri[i][2:] for i, _ in enumerate(_uri)])
        return decoded_uri
