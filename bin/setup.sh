#!/bin/bash

echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install -y imagemagick

echo "Installing LED Matrix driver..."
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
make build-python

echo "Setup complete! Run './bin/run_scoreboard.sh' to start the scoreboard."
