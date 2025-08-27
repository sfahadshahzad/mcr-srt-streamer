# MCR SRT Streamer - Testing Guide

This guide provides step-by-step instructions for setting up a complete environment to test all features of the `mcr-srt-streamer` application, with a special focus on the new SDI Input and Output functionality.

## 1. Prerequisites

Before you begin, ensure you have the following:

- **A Server:** A server running Ubuntu 24.04 LTS or a similar modern Debian-based distribution.
- **Application Installed:** The `mcr-srt-streamer` application should be installed on the server. It is highly recommended to use the provided `setup.sh` script for a clean and automated installation.
- **SDI Hardware:** A GStreamer-compatible SDI capture and playback card. This guide uses the Blackmagic DeckLink series as an example, as they are well-supported by GStreamer. The card must be physically installed in the server.
- **Physical Video Equipment:**
    - To test **SDI Input**: A physical video source (e.g., a camera, VTR, or another device with an SDI output).
    - To test **SDI Output**: A professional video monitor or recording device with an SDI input.
- **Cabling:** Appropriate SDI cables to connect your equipment.

## 2. Verifying GStreamer DeckLink Support

After installation, it's crucial to verify that GStreamer can communicate with your DeckLink hardware.

1.  **Ensure `gst-plugins-bad` is installed:** The `setup.sh` script installs this package, which contains the `decklink` GStreamer elements. If you installed manually, ensure it's present.

2.  **Run `gst-inspect-1.0`:** Open a terminal on the server and run the following command to check for the DeckLink video source element:
    ```bash
    gst-inspect-1.0 decklinkvideosrc
    ```
    If the command returns detailed information about the element (factory details, element properties, etc.), the plugin is installed correctly. If it returns an error like "No such element", the plugin is missing or not in GStreamer's path.

3.  **List Detected Devices (Optional):** You can also try to run a simple pipeline to see if GStreamer detects your device. The application does this automatically, but this is a good manual check.

## 3. Testing SDI Output

This test verifies that the application can take an incoming IP stream and play it out of the SDI hardware.

### Step 3.1: Generate a UDP Test Stream

You need a transport stream over UDP to act as a source. You can use `ffmpeg` on another machine (or on the same machine if powerful enough) to generate a test pattern and send it to a multicast address.

Open a terminal and run the following `ffmpeg` command:

```bash
ffmpeg -re -f lavfi -i smptehdbars=size=1920x1080:rate=25 -f lavfi -i sine=frequency=1000:sample_rate=48000 -c:v libx264 -b:v 8M -c:a aac -b:a 192k -f mpegts "udp://239.1.1.1:5000?pkt_size=1316"
```

**Command Breakdown:**
- `-f lavfi -i smptehdbars`: Generates a 1080p HD color bar test pattern.
- `-f lavfi -i sine`: Generates a 1kHz audio tone.
- `-c:v libx264 -b:v 8M`: Encodes the video to H.264 at 8 Mbps.
- `-c:a aac -b:a 192k`: Encodes the audio to AAC at 192 kbps.
- `-f mpegts "udp://..."`: Muxes into an MPEG Transport Stream and sends it to the multicast address `239.1.1.1` on port `5000`.

This command will run continuously, providing a stable source for your test.

### Step 3.2: Configure SDI Output in the Web UI

1.  Connect a video monitor to the output of your DeckLink card.
2.  Open a web browser and navigate to the `mcr-srt-streamer` dashboard.
3.  Click on the **SDI Output** button in the top navigation bar.
4.  On the "SDI Output Configuration" page, you will see a form to "Start New SDI Output".
5.  In the **UDP Input URI** field, enter the address from the `ffmpeg` command: `udp://239.1.1.1:5000`.
6.  From the **Output Device** dropdown, select the SDI device you want to send the video to.
7.  Click the **Start Output** button.

### Step 3.3: Verify the Output

- The application's UI should show the SDI output as "Running" in the "Active SDI Outputs" table.
- The video monitor connected to your DeckLink card's output should now display the HD color bar test pattern with the 1kHz audio tone.

If this works, your SDI Output functionality is correctly configured.

## 4. Testing SDI Input

This test verifies that the application can capture a signal from the SDI hardware and stream it out over SRT.

### Step 4.1: Connect an SDI Source

1.  Connect your physical SDI video source (e.g., a camera) to an input on your DeckLink card.
2.  Ensure the source is powered on and outputting a standard video format (e.g., 1080i50, 720p50).

### Step 4.2: Configure SDI Input in the Web UI

You can test this as either a **Listener** or a **Caller**. We'll use the Listener form on the main dashboard as an example.

1.  Navigate to the main dashboard of the `mcr-srt-streamer` application.
2.  In the "Start New Listener Stream" form, select **SDI Input** from the "Input Source Type" dropdown.
3.  The form will now display two new fields:
    - **SDI Input Device:** Select the device your source is connected to.
    - **SDI Video Mode:** Select the video format that matches your source (e.g., `1080i50`).
4.  Configure the rest of the SRT parameters as desired (Port, Latency, etc.).
5.  Click the **Start Listener** button.

### Step 4.3: Verify the Stream

1.  The stream should appear in the "Active Streams" list on the dashboard with the status "Waiting for connection".
2.  Use an SRT-capable video player (like VLC, ffplay, or Haivision ProPlayer) to connect to your stream.
    - **URL:** `srt://<your-server-ip>:<listener-port>`
    - Example: `srt://192.168.1.100:10001`
3.  The player should connect, and the stream status on the dashboard should change to "Connected".
4.  You should see and hear the video and audio from your physical SDI source playing in your SRT client.

If this works, your SDI Input functionality is correctly configured.
