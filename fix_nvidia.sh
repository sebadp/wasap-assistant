#!/bin/bash

# Stop on error
set -e

echo "=== NVIDIA Driver Fix Script ==="
echo "This script will: "
echo "1. Purge all existing NVIDIA packages."
echo "2. Install the recommended driver version using ubuntu-drivers autoinstall."
echo "   (Current recommendation appears to be nvidia-driver-590-open)"
echo ""
echo "WARNING: This operation requires sudo privileges and internet access."
echo "You will need to REBOOT after this script completes."
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."

echo "--> Purging existing NVIDIA packages..."
sudo apt-get purge -y '*nvidia*'
sudo apt-get autoremove -y

echo "--> Updating package lists..."
sudo apt-get update

echo "--> Installing recommended drivers and DKMS..."
# Explicitly install the DKMS package to ensure modules are built
sudo apt-get install -y nvidia-driver-590-open nvidia-dkms-590-open

echo ""
echo "=== SUCCESS ==="
echo "Please REBOOT your system now to load the new kernel modules."
echo "After reboot, run 'nvidia-smi' to verify the installation."
