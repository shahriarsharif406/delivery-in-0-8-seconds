#!/bin/bash
set -e
cd "$(dirname "$0")"
GLOW="lutrgb=r='clip((val-205)*4,0,255)':g='clip((val-205)*4,0,255)':b='clip((val-205)*4,0,255)'"
ffmpeg -y -hide_banner -loglevel warning -stats \
  -framerate 24 -start_number 1 -i delivery_frames/f_%04d.png -i delivery_soundtrack.wav \
  -filter_complex "[0:v]format=gbrp,split=3[a][b][c];
[b]${GLOW},gblur=sigma=8[g1];
[c]${GLOW},gblur=sigma=28[g2];
[a][g1]blend=all_mode=screen:all_opacity=0.4[x1];
[x1][g2]blend=all_mode=screen:all_opacity=0.35[x2];
[x2]eq=contrast=1.05:saturation=1.15:brightness=0.03,vignette=angle=PI/8,noise=alls=4:allf=t,fade=t=out:st=14.45:d=0.55,format=yuv420p[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset slow -crf 17 -af volume=0.8,alimiter=limit=0.9 -c:a aac -b:a 256k -shortest -movflags +faststart \
  delivery_in_0.8_seconds_1080p.mp4
ffmpeg -y -hide_banner -loglevel warning -stats -i delivery_in_0.8_seconds_1080p.mp4 \
  -c:v libx264 -preset slow -crf 26 -maxrate 5M -bufsize 10M -pix_fmt yuv420p -c:a aac -b:a 160k -movflags +faststart delivery_in_0.8_seconds_1080p_discord.mp4
ls -la delivery_in_0.8_seconds_*.mp4
