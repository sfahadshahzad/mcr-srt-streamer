$(document).ready(function() {
    const sdiOutputForm = $('#sdi-output-form');
    const sdiOutputsTableBody = $('#sdi-outputs-table-body');
    const uriError = $('#uri-error');
    const deviceIdError = $('#device_id-error');

    // --- Initial Data Loading ---

    function loadSdiDevices() {
        $.ajax({
            url: '/sdi/api/devices',
            type: 'GET',
            success: function(data) {
                const deviceSelect = $('#device_id');
                deviceSelect.empty();
                if (data.outputs && data.outputs.length > 0) {
                    $.each(data.outputs, function(index, device) {
                        deviceSelect.append(new Option(device.name, device.device_id));
                    });
                } else {
                    deviceSelect.append(new Option('No output devices found', ''));
                    deviceSelect.prop('disabled', true);
                    sdiOutputForm.find('button[type="submit"]').prop('disabled', true);
                }
            },
            error: function(xhr) {
                console.error("Failed to load SDI devices:", xhr.responseText);
                showAlert('Failed to load SDI devices.', 'danger');
            }
        });
    }

    function updateActiveOutputs() {
        $.ajax({
            url: '/sdi/api/outputs',
            type: 'GET',
            success: function(data) {
                sdiOutputsTableBody.empty();
                if (Object.keys(data).length > 0) {
                    $.each(data, function(id, output) {
                        const uptime = output.start_time ? formatUptime(output.start_time) : 'N/A';
                        const statusClass = getStatusClass(output.status);
                        const row = `
                            <tr>
                                <td>${output.output_id}</td>
                                <td><span class="badge ${statusClass}">${output.status || 'Unknown'}</span></td>
                                <td>${output.uri || 'N/A'}</td>
                                <td>${uptime}</td>
                                <td>
                                    <button class="btn btn-danger btn-sm stop-sdi-btn" data-output-id="${output.output_id}">Stop</button>
                                </td>
                            </tr>
                        `;
                        sdiOutputsTableBody.append(row);
                    });
                } else {
                    sdiOutputsTableBody.append('<tr><td colspan="5" class="text-center">No active SDI outputs.</td></tr>');
                }
            },
            error: function(xhr) {
                console.error("Failed to update active outputs:", xhr.responseText);
                sdiOutputsTableBody.find('td').text('Error loading data.');
            }
        });
    }

    // --- Form Submission ---

    sdiOutputForm.on('submit', function(e) {
        e.preventDefault();
        clearErrors();

        $.ajax({
            url: '/sdi/api/start',
            type: 'POST',
            data: sdiOutputForm.serialize(),
            success: function(response) {
                showAlert(response.message, 'success');
                sdiOutputForm[0].reset();
                updateActiveOutputs();
            },
            error: function(xhr) {
                const response = xhr.responseJSON;
                if (response && response.errors) {
                    if (response.errors.uri) {
                        $('#uri').addClass('is-invalid');
                        uriError.text(response.errors.uri.join(', '));
                    }
                    if (response.errors.device_id) {
                        $('#device_id').addClass('is-invalid');
                        deviceIdError.text(response.errors.device_id.join(', '));
                    }
                } else {
                    const message = response ? response.message : 'An unknown error occurred.';
                    showAlert(message, 'danger');
                }
            }
        });
    });

    // --- Event Handlers ---

    sdiOutputsTableBody.on('click', '.stop-sdi-btn', function() {
        const outputId = $(this).data('output-id');
        if (confirm(`Are you sure you want to stop SDI Output ${outputId}?`)) {
            $.ajax({
                url: '/sdi/api/stop',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ output_id: outputId }),
                success: function(response) {
                    showAlert(response.message, 'success');
                    updateActiveOutputs();
                },
                error: function(xhr) {
                    const message = xhr.responseJSON ? xhr.responseJSON.message : 'Failed to stop SDI output.';
                    showAlert(message, 'danger');
                }
            });
        }
    });

    // --- Utility Functions ---

    function clearErrors() {
        $('.is-invalid').removeClass('is-invalid');
        $('.invalid-feedback').text('');
    }

    function formatUptime(startTime) {
        const now = new Date().getTime() / 1000;
        let seconds = Math.floor(now - startTime);
        if (isNaN(seconds) || seconds < 0) return '0s';

        let d = Math.floor(seconds / (3600 * 24));
        let h = Math.floor(seconds % (3600 * 24) / 3600);
        let m = Math.floor(seconds % 3600 / 60);
        let s = Math.floor(seconds % 60);

        return [
            d > 0 ? `${d}d` : '',
            h > 0 ? `${h}h` : '',
            m > 0 ? `${m}m` : '',
            `${s}s`
        ].filter(Boolean).join(' ');
    }

    function getStatusClass(status) {
        if (!status) return 'bg-secondary';
        status = status.toLowerCase();
        if (status.includes('running') || status.includes('connected')) return 'bg-success';
        if (status.includes('error') || status.includes('failed')) return 'bg-danger';
        if (status.includes('starting') || status.includes('stopping')) return 'bg-warning';
        return 'bg-info';
    }

    function showAlert(message, type = 'info') {
        const alertContainer = $('.container-fluid').first();
        const alert = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
        // Prepend to the main container, so it's visible
        alertContainer.prepend(alert);
        // Auto-dismiss after 5 seconds
        window.setTimeout(function() {
            $(".alert").fadeTo(500, 0).slideUp(500, function(){
                $(this).remove();
            });
        }, 5000);
    }

    // --- Initialization ---
    loadSdiDevices();
    updateActiveOutputs();
    setInterval(updateActiveOutputs, 5000); // Refresh every 5 seconds
});
