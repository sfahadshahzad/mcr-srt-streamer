# /opt/mcr-srt-streamer/app/sdi_manager.py

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib, GObject
import threading
import logging
import time
from datetime import datetime, timedelta
import re

# Initialize GStreamer
Gst.init(None)

try:
    import gevent
except ImportError:
    logging.getLogger(__name__).critical("gevent is not installed, which is required for the Gunicorn worker.")
    gevent = None


class SDIManager:
    def __init__(self):
        self.active_sdi_outputs = {}
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        if not self.logger.hasHandlers():
            log_handler = logging.StreamHandler()
            log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            log_handler.setFormatter(log_formatter)
            self.logger.addHandler(log_handler)
            self.logger.setLevel(logging.INFO)

        self.logger.info("SDIManager Initialized.")

    def start_glib_loop(self):
        """Public method to be called from wsgi.py to start the non-blocking loop."""
        if not gevent:
            self.logger.critical("Cannot start GLib loop because gevent is not available.")
            return
        self.logger.info("Spawning gevent greenlet for SDIManager's GLib loop.")
        gevent.spawn(self._run_glib_loop_non_blocking)

    def _run_glib_loop_non_blocking(self):
        self.logger.info("Starting non-blocking GLib main context loop for SDIManager...")
        context = GLib.MainContext.default()
        while True:
            try:
                context.iteration(False)
                gevent.sleep(0.01)
            except Exception as e:
                self.logger.error(f"Error in SDIManager's non-blocking GLib loop: {e}", exc_info=True)
                gevent.sleep(1)

    def _schedule_null_state(self, pipeline, output_id):
        if pipeline:
            self.logger.info(f"Scheduling state change to NULL for SDI output {output_id} via idle_add.")
            def set_null_safe(p, k):
                self.logger.debug(f"Executing async set_state(NULL) for SDI output {k}...")
                try:
                    p.set_state(Gst.State.NULL)
                except Exception as e_state:
                    self.logger.error(f"Exception during async set_state(NULL) for SDI output {k}: {e_state}", exc_info=True)
                return False
            GLib.idle_add(set_null_safe, pipeline, output_id, priority=GLib.PRIORITY_DEFAULT)
            return True
        return False

    def _cleanup_sdi_output_resources(self, output_id, bus_obj):
        self.logger.info(f"Performing final cleanup for SDI output {output_id} (bus watch, etc.).")
        if bus_obj:
            try:
                bus_obj.remove_signal_watch()
            except Exception as bus_e:
                self.logger.warning(f"Error removing signal watch for SDI output {output_id}: {bus_e}")

    def _on_sdi_bus_message(self, bus, message, output_id):
        t = message.type
        if t in (Gst.MessageType.EOS, Gst.MessageType.ERROR):
            if t == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                self.logger.error(f"BUS_MSG: GStreamer error on SDI output {output_id}: {err.message}. Debug: {debug}")
                status = f"Error: {err.message}"
            else:
                self.logger.info(f"BUS_MSG: EOS received for SDI output {output_id}.")
                status = "Ended (EOS)"

            with self.lock:
                if output_id in self.active_sdi_outputs:
                    self.active_sdi_outputs[output_id]["status"] = status
                    self.active_sdi_outputs[output_id]["stopping"] = True
                    pipeline = self.active_sdi_outputs[output_id].get("pipeline")
                    self._schedule_null_state(pipeline, output_id)
        return True

    def detect_sdi_devices(self):
        """
        Detects available DeckLink SDI devices.
        For now, this will return a placeholder.
        """
        self.logger.info("Detecting SDI devices (placeholder)...")
        # In a real implementation, Gst.DeviceMonitor would be used.
        # This placeholder is for development without hardware.
        return {
            "outputs": [
                {"device_id": 0, "name": "DeckLink Mini Monitor 4K (1)"},
                {"device_id": 1, "name": "DeckLink Mini Monitor 4K (2)"},
            ],
            "inputs": [
                 {"device_id": 0, "name": "DeckLink Mini Recorder 4K (1)"},
            ]
        }

    def start_sdi_output(self, config):
        """
        Starts an SDI output stream from a UDP source.
        """
        pipeline = None
        try:
            output_id = int(config["device_id"])
            uri = config["uri"]
            if not re.match(r"udp://@?[\w\d\.-]+:\d+", uri):
                 raise ValueError("Invalid UDP URI format.")
        except (KeyError, ValueError, TypeError) as e:
            return False, f"Invalid configuration: {e}"

        self.logger.info(f"Starting SDI Output {output_id} for URI {uri}")

        with self.lock:
            if output_id in self.active_sdi_outputs:
                self.logger.warning(f"SDI Output {output_id} is already active. Stopping it first.")
                self.stop_sdi_output(str(output_id))
                time.sleep(0.5) # Give it a moment to stop

        # This pipeline decodes a TS stream and outputs to SDI
        # It assumes H.264 video and AAC audio.
        pipeline_str = (
            f'udpsrc uri="{uri}" ! '
            f'tsdemux name=demux '
            f'demux. ! queue ! h264parse ! avdec_h264 ! videoconvert ! decklinkvideosink device-number={output_id} '
            f'demux. ! queue ! aacparse ! avdec_aac ! audioconvert ! decklinkaudiosink device-number={output_id}'
        )
        self.logger.debug(f"SDI Output {output_id} pipeline: {pipeline_str}")

        try:
            pipeline = Gst.parse_launch(pipeline_str)
        except GLib.Error as e:
            self.logger.error(f"Failed to parse SDI output pipeline for device {output_id}: {e}")
            return False, f"Pipeline parse error: {e}"

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_sdi_bus_message, output_id)

        output_info = {
            "pipeline": pipeline,
            "bus": bus,
            "config": config,
            "output_id": output_id,
            "status": "Starting",
            "stopping": False,
            "start_time": time.time(),
        }

        with self.lock:
            self.active_sdi_outputs[output_id] = output_info

        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self.logger.error(f"Failed to set SDI output {output_id} to PLAYING.")
            with self.lock:
                self.active_sdi_outputs.pop(output_id, None)
            self._cleanup_sdi_output_resources(output_id, bus)
            return False, f"Failed to start pipeline for SDI Output {output_id}."

        with self.lock:
            if output_id in self.active_sdi_outputs:
                self.active_sdi_outputs[output_id]["status"] = "Running"

        return True, f"SDI Output {output_id} started successfully."

    def stop_sdi_output(self, output_id_str):
        """
        Stops an SDI output stream.
        """
        try:
            output_id = int(output_id_str)
        except (ValueError, TypeError):
            return False, "Invalid Output ID."

        self.logger.info(f"Request received to stop SDI output: {output_id}")

        with self.lock:
            output_info = self.active_sdi_outputs.pop(output_id, None)

        if not output_info:
            return False, f"SDI Output {output_id} not found or already stopped."

        pipeline = output_info.get("pipeline")
        bus = output_info.get("bus")

        if pipeline:
            output_info["stopping"] = True
            self._schedule_null_state(pipeline, output_id)
        else:
            self._cleanup_sdi_output_resources(output_id, bus)

        return True, f"SDI Output {output_id} stopped."

    def get_active_sdi_outputs(self):
        """
        Returns a dictionary of active SDI outputs for the dashboard.
        """
        with self.lock:
            # Create a deep copy to avoid issues with concurrent modification
            return {k: v.copy() for k, v in self.active_sdi_outputs.items()}

    def shutdown(self):
        self.logger.info("Shutting down SDIManager...")
        with self.lock:
            keys_to_stop = list(self.active_sdi_outputs.keys())

        for key in keys_to_stop:
            self.stop_sdi_output(str(key))

        self.logger.info("SDIManager shutdown sequence complete.")
