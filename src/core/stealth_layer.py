import random
import json
from playwright.async_api import BrowserContext

class StealthLayer:
    def __init__(self):
        self.fingerprints = self._load_fingerprints()

    def _load_fingerprints(self):
        """
        Load a diverse set of realistic browser fingerprints.
        These simulate different hardware/software configurations.
        """
        return [
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "screen": {"width": 1920, "height": 1080},
                "locale": "en-US",
                "timezone": "America/New_York",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "platform": "Win32",
                "memory": 8
            },
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "screen": {"width": 2560, "height": 1440},
                "locale": "en-GB",
                "timezone": "Europe/London",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "platform": "Win32",
                "memory": 16
            },
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "screen": {"width": 1366, "height": 768},
                "locale": "en-US",
                "timezone": "America/Los_Angeles",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "platform": "Win32",
                "memory": 8
            },
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "screen": {"width": 1536, "height": 864},
                "locale": "de-DE",
                "timezone": "Europe/Berlin",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (AMD, AMD Radeon RX 580 Series Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "platform": "Win32",
                "memory": 16
            },
            {
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "screen": {"width": 1440, "height": 900},
                "locale": "en-US",
                "timezone": "America/Chicago",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (Apple, Apple M1, OpenGL 4.1)",
                "platform": "MacIntel",
                "memory": 8
            },
            {
                "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "screen": {"width": 2560, "height": 1600},
                "locale": "en-US",
                "timezone": "America/Denver",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (Apple, Apple M2 Pro, OpenGL 4.1)",
                "platform": "MacIntel",
                "memory": 16
            },
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
                "screen": {"width": 1920, "height": 1200},
                "locale": "fr-FR",
                "timezone": "Europe/Paris",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "platform": "Win32",
                "memory": 16
            },
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "screen": {"width": 3840, "height": 2160},
                "locale": "ja-JP",
                "timezone": "Asia/Tokyo",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "platform": "Win32",
                "memory": 32
            },
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "screen": {"width": 1680, "height": 1050},
                "locale": "es-ES",
                "timezone": "Europe/Madrid",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "platform": "Win32",
                "memory": 16
            },
            {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "screen": {"width": 1280, "height": 720},
                "locale": "pt-BR",
                "timezone": "America/Sao_Paulo",
                "vendor": "Google Inc.",
                "renderer": "ANGLE (Intel, Intel(R) HD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "platform": "Win32",
                "memory": 4
            }
        ]

    def get_random_fingerprint(self):
        return random.choice(self.fingerprints)

    async def apply_stealth(self, context: BrowserContext, fingerprint: dict):
        """
        Applies advanced stealth techniques to a browser context.
        """
        # 1. Mask Webdriver property
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Also delete if already set
            delete navigator.__proto__.webdriver;
        """)

        # 2. Spoof WebGL (both WebGL1 and WebGL2)
        webgl_script = f"""
            const spoofWebGL = (proto) => {{
                const getParameter = proto.getParameter;
                proto.getParameter = function(parameter) {{
                    // UNMASKED_VENDOR_WEBGL
                    if (parameter === 37445) {{
                        return '{fingerprint['vendor']}';
                    }}
                    // UNMASKED_RENDERER_WEBGL
                    if (parameter === 37446) {{
                        return '{fingerprint['renderer']}';
                    }}
                    return getParameter.apply(this, arguments);
                }};
            }};
            
            // Apply to both WebGL1 and WebGL2
            if (typeof WebGLRenderingContext !== 'undefined') {{
                spoofWebGL(WebGLRenderingContext.prototype);
            }}
            if (typeof WebGL2RenderingContext !== 'undefined') {{
                spoofWebGL(WebGL2RenderingContext.prototype);
            }}
        """
        await context.add_init_script(webgl_script)

        # 3. Spoof Plugins (realistic plugin list)
        await context.add_init_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                        {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}
                    ];
                    plugins.length = 3;
                    return plugins;
                }
            });
            
            Object.defineProperty(navigator, 'mimeTypes', {
                get: () => {
                    const mimes = [
                        {type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format'},
                        {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format'}
                    ];
                    mimes.length = 2;
                    return mimes;
                }
            });
        """)

        # 4. Hardware Concurrency (consistent with fingerprint)
        cores = fingerprint.get('memory', 8) // 2  # Rough correlation
        if cores < 2:
            cores = 2
        await context.add_init_script(f"""
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {cores}
            }});
        """)
        
        # 5. Device Memory
        memory = fingerprint.get('memory', 8)
        await context.add_init_script(f"""
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {memory}
            }});
        """)
        
        # 6. Platform spoofing
        platform = fingerprint.get('platform', 'Win32')
        await context.add_init_script(f"""
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{platform}'
            }});
        """)
        
        # 7. Canvas Noise (subtle noise that doesn't break visuals)
        await context.add_init_script("""
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            const originalToBlob = HTMLCanvasElement.prototype.toBlob;
            const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
            
            // Generate a consistent noise seed per session
            const noiseSeed = Math.random() * 0.01;
            
            const addNoise = (imageData) => {
                const data = imageData.data;
                for (let i = 0; i < Math.min(data.length, 40); i += 4) {
                    // Very subtle noise
                    data[i] = Math.max(0, Math.min(255, data[i] + (noiseSeed * 10 - 5)));
                }
                return imageData;
            };
            
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                const context = this.getContext('2d');
                if (context && this.width > 0 && this.height > 0) {
                    try {
                        const imageData = context.getImageData(0, 0, Math.min(this.width, 10), Math.min(this.height, 1));
                        addNoise(imageData);
                        context.putImageData(imageData, 0, 0);
                    } catch (e) {}
                }
                return originalToDataURL.apply(this, arguments);
            };
            
            CanvasRenderingContext2D.prototype.getImageData = function() {
                const imageData = originalGetImageData.apply(this, arguments);
                return addNoise(imageData);
            };
        """)

        # 8. Audio Fingerprinting Noise (AudioContext and OscillatorNode)
        await context.add_init_script("""
            // Noise for AnalyserNode
            const originalGetFloatFrequencyData = AnalyserNode.prototype.getFloatFrequencyData;
            AnalyserNode.prototype.getFloatFrequencyData = function(array) {
                const result = originalGetFloatFrequencyData.apply(this, arguments);
                const noise = Math.random() * 0.0001;
                for (let i = 0; i < array.length; i++) {
                    array[i] += noise;
                }
                return result;
            };
            
            const originalGetByteFrequencyData = AnalyserNode.prototype.getByteFrequencyData;
            AnalyserNode.prototype.getByteFrequencyData = function(array) {
                const result = originalGetByteFrequencyData.apply(this, arguments);
                const noise = Math.floor(Math.random() * 2);
                for (let i = 0; i < Math.min(array.length, 10); i++) {
                    array[i] = Math.max(0, Math.min(255, array[i] + noise));
                }
                return result;
            };
            
            // Noise for AudioBuffer (channel data)
            const originalGetChannelData = AudioBuffer.prototype.getChannelData;
            AudioBuffer.prototype.getChannelData = function(channel) {
                const data = originalGetChannelData.apply(this, arguments);
                const noise = Math.random() * 0.0000001;
                for (let i = 0; i < Math.min(data.length, 10); i++) {
                    data[i] += noise;
                }
                return data;
            };
        """)

        # 9. WebRTC Leak Prevention (block local IP exposure)
        await context.add_init_script("""
            // Store original RTCPeerConnection
            const OriginalRTCPeerConnection = window.RTCPeerConnection || window.webkitRTCPeerConnection;
            
            if (OriginalRTCPeerConnection) {
                window.RTCPeerConnection = function(config, constraints) {
                    // Block ICE candidates that leak local IPs
                    const pc = new OriginalRTCPeerConnection(config, constraints);
                    
                    const originalAddIceCandidate = pc.addIceCandidate.bind(pc);
                    pc.addIceCandidate = function(candidate) {
                        if (candidate && candidate.candidate) {
                            // Block local/private IP candidates
                            const localIpPattern = /((192\\.168\\.)|(10\\.)|(172\\.(1[6-9]|2[0-9]|3[0-1])\\.))/;
                            if (localIpPattern.test(candidate.candidate)) {
                                return Promise.resolve();
                            }
                        }
                        return originalAddIceCandidate(candidate);
                    };
                    
                    return pc;
                };
                
                window.RTCPeerConnection.prototype = OriginalRTCPeerConnection.prototype;
                window.webkitRTCPeerConnection = window.RTCPeerConnection;
            }
        """)
        
        # 10. Hide automation-related Chrome features
        await context.add_init_script("""
            // Remove cdc_ properties from window
            const deleteAutomationProps = () => {
                const props = Object.keys(window).filter(key => 
                    key.includes('cdc_') || 
                    key.includes('$cdc_') ||
                    key.includes('selenium') ||
                    key.includes('webdriver')
                );
                props.forEach(prop => {
                    try { delete window[prop]; } catch(e) {}
                });
            };
            deleteAutomationProps();
            
            // Override chrome.runtime to appear as normal browser
            if (!window.chrome) {
                window.chrome = {};
            }
            window.chrome.runtime = {
                connect: () => {},
                sendMessage: () => {}
            };
            
            // Hide permission automation
            const originalQuery = navigator.permissions.query;
            navigator.permissions.query = (parameters) => {
                if (parameters.name === 'notifications') {
                    return Promise.resolve({ state: Notification.permission });
                }
                return originalQuery(parameters);
            };
        """)
        
        # 11. Spoof languages
        locale = fingerprint.get('locale', 'en-US')
        lang = locale.split('-')[0]
        await context.add_init_script(f"""
            Object.defineProperty(navigator, 'language', {{
                get: () => '{locale}'
            }});
            Object.defineProperty(navigator, 'languages', {{
                get: () => ['{locale}', '{lang}']
            }});
        """)

