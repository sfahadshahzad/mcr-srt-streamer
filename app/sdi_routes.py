# /opt/mcr-srt-streamer/app/sdi_routes.py

from flask import Blueprint, render_template, request, jsonify, current_app
from app.forms import SDIOutputForm

sdi_bp = Blueprint('sdi_bp', __name__)

@sdi_bp.route('/sdi_out')
def sdi_out_page():
    """
    Renders the main page for SDI output configuration and management.
    """
    form = SDIOutputForm()
    # The device choices will be populated dynamically via JavaScript
    return render_template('sdi_out.html', title='SDI Output', form=form)

@sdi_bp.route('/sdi/api/devices', methods=['GET'])
def get_sdi_devices():
    """
    API endpoint to get a list of available SDI input and output devices.
    """
    sdi_manager = current_app.sdi_manager
    try:
        devices = sdi_manager.detect_sdi_devices()
        return jsonify(devices)
    except Exception as e:
        current_app.logger.error(f"Failed to detect SDI devices: {e}", exc_info=True)
        return jsonify(error=str(e)), 500

@sdi_bp.route('/sdi/api/outputs', methods=['GET'])
def get_active_outputs():
    """
    API endpoint to get a list of active SDI outputs.
    """
    sdi_manager = current_app.sdi_manager
    active_outputs = sdi_manager.get_active_sdi_outputs()
    # Sanitize the dictionary before returning
    safe_outputs = {}
    for key, val in active_outputs.items():
        safe_outputs[key] = {
            "output_id": val.get("output_id"),
            "status": val.get("status"),
            "uri": val.get("config", {}).get("uri"),
            "start_time": val.get("start_time"),
        }
    return jsonify(safe_outputs)

@sdi_bp.route('/sdi/api/start', methods=['POST'])
def start_output():
    """
    API endpoint to start a new SDI output.
    """
    sdi_manager = current_app.sdi_manager
    form = SDIOutputForm(request.form)

    # Manually populate choices for validation, as they are dynamic
    devices = sdi_manager.detect_sdi_devices()
    form.device_id.choices = [(str(d['device_id']), d['name']) for d in devices.get('outputs', [])]

    if form.validate():
        config = {
            "device_id": form.device_id.data,
            "uri": form.uri.data,
        }
        success, message = sdi_manager.start_sdi_output(config)
        if success:
            return jsonify(success=True, message=message)
        else:
            return jsonify(success=False, message=message), 400
    else:
        return jsonify(success=False, errors=form.errors), 400

@sdi_bp.route('/sdi/api/stop', methods=['POST'])
def stop_output():
    """
    API endpoint to stop an active SDI output.
    """
    sdi_manager = current_app.sdi_manager
    data = request.get_json()
    output_id = data.get('output_id')
    if not output_id:
        return jsonify(success=False, message="Missing output_id"), 400

    success, message = sdi_manager.stop_sdi_output(str(output_id))
    if success:
        return jsonify(success=True, message=message)
    else:
        return jsonify(success=False, message=message), 400
