#!/bin/sh
echo "Installing GrumpyScreen..."
mkdir /usr/data/grumpyscreen/
echo "Downloading GrumpyScreen..."
curl -k -o /usr/data/grumpyscreen/grumpyscreen.tar.xz https://github.com/pellcorp/grumpyscreen/releases/download/main/grumpyscreen.tar.gz
tar -xvf /usr/data/grumpyscreen/grumpyscreen.tar.xz -C /usr/data/grumpyscreen/
mv /usr/data/grumpyscreen/./grumpyscreen/grumpyscreen /usr/data/grumpyscreen/grumpyscreen
rm /usr/data/grumpyscreen/.
rm /usr/data/grumpyscreen/grumpyscreen.tar.xz
chmod 755 grumpyscreen
echo "GrumpyScreen has been successfully installed!"