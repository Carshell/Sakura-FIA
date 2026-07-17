#include <WiFi.h>
#include <ESPAsyncWebServer.h>

const char* ssid = "Drone_Companion_AP";
const char* password = "123456789_FPV";

AsyncWebServer server(80);

// RC: Roll, Pitch, Throttle, Yaw, AUX1(ARM), AUX2(ANGLE), AUX3, AUX4
const uint16_t AUX1_DISARM = 1000;
const uint16_t AUX1_ARM = 2000;
const uint16_t AUX2_ANGLE = 1500;

uint16_t rcChannels[8] = {1500, 1500, 1000, 1500, AUX1_DISARM, AUX2_ANGLE, 1500, 1500};

unsigned long lastSendTime = 0;
const unsigned long sendInterval = 20; // ~50 Hz MSP

unsigned long lastNetworkActionTime = 0;
const unsigned long failsafeTimeout = 1000;
bool inFailsafe = false;

// HC-SR04
const int TRIG_PIN = 4;
const int ECHO_PIN = 5;
const float OBSTACLE_DISARM_CM = 30.0;
const unsigned long SONAR_INTERVAL_MS = 80;
unsigned long lastSonarReadTime = 0;
float lastDistanceCm = -1.0;
bool obstacleTooClose = false;

void applyDisarm() {
    rcChannels[4] = AUX1_DISARM;
    rcChannels[2] = 1000;
    rcChannels[0] = 1500;
    rcChannels[1] = 1500;
    rcChannels[3] = 1500;
}

float readDistanceCm() {
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    unsigned long duration = pulseIn(ECHO_PIN, HIGH, 25000);
    if (duration == 0) {
        return -1.0;
    }
    return (duration * 0.0343f) / 2.0f;
}

void updateSonar() {
    if (millis() - lastSonarReadTime < SONAR_INTERVAL_MS) {
        return;
    }
    lastSonarReadTime = millis();

    float cm = readDistanceCm();
    lastDistanceCm = cm;

    bool wasTooClose = obstacleTooClose;
    // -1 = помилка виміру, не дизармимо
    obstacleTooClose = (cm > 0.0f && cm < OBSTACLE_DISARM_CM);

    if (obstacleTooClose) {
        applyDisarm();
        if (!wasTooClose) {
            Serial.print("Obstacle ");
            Serial.print(cm);
            Serial.println(" cm -> DISARM");
        }
    }
}

const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE HTML>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>FPV Web RC</title>
  <style>
    body { 
      background: #111; color: white; text-align: center; font-family: sans-serif; 
      margin: 0; padding: 0; overflow: hidden; /* Блокуємо скрол екрана */
      user-select: none; -webkit-user-select: none; touch-action: none;
    }
    .top-bar { margin-top: 15px; }
    .btn { padding: 15px 35px; font-size: 20px; font-weight: bold; border: none; border-radius: 8px; margin: 0 10px; }
    .arm-btn { background: #d32f2f; color: white; }
    .disarm-btn { background: #555; color: white; }
    
    .joy-container { 
      display: flex; justify-content: space-around; align-items: center; 
      width: 100vw; height: 70vh; margin-top: 20px;
    }
    .zone { 
      width: 160px; height: 160px; background: rgba(255,255,255,0.05); 
      border-radius: 50%; position: relative; border: 2px solid #444; 
    }
    .stick { 
      width: 60px; height: 60px; background: rgba(255,255,255,0.7); 
      border-radius: 50%; position: absolute; box-shadow: 0 0 15px rgba(0,0,0,0.8);
      left: 50%; top: 50%; margin-left: -30px; margin-top: -30px;
    }
  </style>
</head>
<body>
  <div class="top-bar">
    <button class="btn arm-btn" onclick="fetch('/cmd?arm=1')">ARM</button>
    <button class="btn disarm-btn" onclick="fetch('/cmd?arm=0')">DISARM</button>
  </div>
  
  <div class="joy-container">
    <div id="left-zone" class="zone"><div id="left-stick" class="stick"></div></div>
    <div id="right-zone" class="zone"><div id="right-stick" class="stick"></div></div>
  </div>

  <script>
    let ch = {r:1500, p:1500, t:1000, y:1500};
    
    function setupJoystick(zoneId, stickId, isLeft) {
      const zone = document.getElementById(zoneId);
      const stick = document.getElementById(stickId);
      const maxR = 80; 
      let active = false;

      if(isLeft) stick.style.transform = `translate(0px, ${maxR}px)`;

      zone.addEventListener('touchstart', (e) => { active = true; move(e); }, {passive: false});
      zone.addEventListener('touchmove', move, {passive: false});
      zone.addEventListener('touchend', end);

      function move(e) {
        e.preventDefault();
        if(!active) return;
        
        let touch = e.targetTouches[0];
        let rect = zone.getBoundingClientRect();
        let cx = rect.left + maxR;
        let cy = rect.top + maxR;
        
        let dx = touch.clientX - cx;
        let dy = touch.clientY - cy;
        
        let dist = Math.sqrt(dx*dx + dy*dy);
        if(dist > maxR) { dx = dx * maxR / dist; dy = dy * maxR / dist; }
        
        stick.style.transform = `translate(${dx}px, ${dy}px)`;
        
        let valX = Math.round(1500 + (dx / maxR) * 500);
        let valY = Math.round(1500 - (dy / maxR) * 500); 

        if(isLeft) {
          ch.y = valX; 
          ch.t = (valY < 1000) ? 1000 : valY; 
        } else {
          ch.r = valX; 
          ch.p = valY; 
        }
      }

      function end() {
        active = false;
        if(isLeft) {
          stick.style.transform = `translate(0px, ${maxR}px)`;
          ch.y = 1500; ch.t = 1000;
        } else {
          stick.style.transform = `translate(0px, 0px)`;
          ch.r = 1500; ch.p = 1500;
        }
      }
    }

    setupJoystick('left-zone', 'left-stick', true);
    setupJoystick('right-zone', 'right-stick', false);

    setInterval(() => {
      fetch(`/update?r=${ch.r}&p=${ch.p}&t=${ch.t}&y=${ch.y}`);
    }, 50);
  </script>
</body>
</html>
)rawliteral";


void sendMSP_SetRawRC(uint16_t* channels, uint8_t channelCount) {
    uint8_t payloadSize = channelCount * 2; 
    uint8_t mspPacket[6 + payloadSize + 1]; 
    
    mspPacket[0] = '$'; mspPacket[1] = 'M'; mspPacket[2] = '<';
    mspPacket[3] = payloadSize; mspPacket[4] = 200;
    
    uint8_t checksum = mspPacket[3] ^ mspPacket[4];
    uint8_t idx = 5;
    
    for (uint8_t i = 0; i < channelCount; i++) {
        mspPacket[idx] = channels[i] & 0xFF;
        checksum ^= mspPacket[idx++];
        mspPacket[idx] = (channels[i] >> 8) & 0xFF;
        checksum ^= mspPacket[idx++];
    }
    
    mspPacket[idx] = checksum; 
    Serial1.write(mspPacket, sizeof(mspPacket));
}

void setup() {
    Serial.begin(115200); 
    Serial1.begin(115200, SERIAL_8N1, RX, TX); // RX/TX під вашу розпіновку

    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    digitalWrite(TRIG_PIN, LOW);

    WiFi.softAP(ssid, password);
    Serial.println("AP Started");
    Serial.println("HC-SR04: TRIG=4 ECHO=5");

    server.on("/", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send_P(200, "text/html", index_html);
    });

    server.on("/cmd", HTTP_GET, [](AsyncWebServerRequest *request){
        lastNetworkActionTime = millis(); 
        inFailsafe = false;
        
        if (request->hasParam("arm")) {
            if (request->getParam("arm")->value() == "1") {
                if (obstacleTooClose) {
                    applyDisarm();
                    request->send(200, "text/plain", "BLOCKED: obstacle");
                    return;
                }
                rcChannels[4] = AUX1_ARM;
                rcChannels[2] = 1000;
            } else {
                applyDisarm();
            }
        }
        rcChannels[5] = AUX2_ANGLE;
        request->send(200, "text/plain", "OK");
    });

    server.on("/update", HTTP_GET, [](AsyncWebServerRequest *request){
        lastNetworkActionTime = millis(); 
        inFailsafe = false;
        
        if (request->hasParam("r")) rcChannels[0] = request->getParam("r")->value().toInt();
        if (request->hasParam("p")) rcChannels[1] = request->getParam("p")->value().toInt();
        if (request->hasParam("t")) rcChannels[2] = request->getParam("t")->value().toInt();
        if (request->hasParam("y")) rcChannels[3] = request->getParam("y")->value().toInt();

        if (obstacleTooClose) {
            applyDisarm();
        }
        rcChannels[5] = AUX2_ANGLE;

        request->send(200, "text/plain", "OK");
    });

    server.begin();
    lastNetworkActionTime = millis();
}

void loop() {
    updateSonar();

    bool noClients = (WiFi.softAPgetStationNum() == 0);
    bool timeout = (millis() - lastNetworkActionTime > failsafeTimeout);

    if (noClients || timeout) {
        if (!inFailsafe) {
            inFailsafe = true;
            Serial.println("Failsafe: lost link, DISARM");
        }
        applyDisarm();
    }

    rcChannels[5] = AUX2_ANGLE;

    if (millis() - lastSendTime >= sendInterval) {
        lastSendTime = millis();
        sendMSP_SetRawRC(rcChannels, 8);
    }
}