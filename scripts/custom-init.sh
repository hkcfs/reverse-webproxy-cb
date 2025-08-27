#!/bin/bash
echo "Creating symlink and setting permissions for downloads folder..."

# Set permissions for the mounted volume
chown -R 1000:1000 /config/Desktop/Downloads

# Remove existing Downloads to avoid conflicts, then create the symlink
rm -rf /config/Downloads
ln -s /config/Desktop/Downloads /config/Downloads

echo "Symlink created and permissions set successfully."

