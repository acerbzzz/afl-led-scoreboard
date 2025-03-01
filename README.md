# AFL LED Scoreboard 🏉💡

A real-time **AFL scoreboard** using a **64x32 RGB LED matrix**, powered by the **Squiggle API**.

## Features
✅ **Live scores** (goals, behinds, total points)  
✅ **Team logos** displayed  
✅ **Quarter and game clock**  
✅ **Auto-updates every 10 seconds**  

## Installation 📌
### **1. Clone the Repository**
```bash
git clone https://github.com/yourusername/afl-led-scoreboard.git
cd afl-led-scoreboard
```

### **2. Install Dependencies**
```bash
sudo apt-get update
sudo apt-get install -y imagemagick
```

### **3. Install LED Matrix Driver**
```bash
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
make build-python
```

### **4. Run the Scoreboard**
```bash
./bin/run_scoreboard.sh
``"
