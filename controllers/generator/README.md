# HP 33120A Web Controller

Photographic Classic and Modern web interfaces for an HP/Agilent 33120A function/arbitrary waveform generator. It uses the Fischer Instrument Suite shared USB-GPIB broker so multiple instruments can safely share one adapter.

## Highlights

- Sine, square, triangle and ramp waveform setup
- Frequency, amplitude, offset and assumed-load controls
- Rotary frequency knob with selectable Hz increment
- Sweep setup, reusable presets, spacing and increment controls
- Classic photographic front panel and responsive Modern view
- Simulation follows staged settings; the primary readback changes only after verified instrument readback
- Explicit Apply actions, origin checks, serialized broker access and post-write verification
- Local HTML manual at `/generator/assets/docs.html`

## Recommended installation

Install it from the **Add instruments** page in the Fischer Instrument Suite. The catalog installer creates the isolated service on port 8084, installs dependencies, runs tests, registers navigation and preserves removal support.

## Development simulation

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python generator_app.py --simulate
```

Open `http://127.0.0.1:8084/generator/classic`. Simulation never opens the USB-GPIB adapter.

## Test

```bash
venv/bin/python -m unittest discover -s . -p 'test_*.py'
```

## Hardware and safety

The application reports configured instrument values; it does not measure output voltage. Confirm the physical load and instrument state before applying changes. Sweep setup and sweep start are separate actions.

## Credits

Original HP 33120A photograph supplied by Rick Fischer. See `hp33120a/static/ATTRIBUTION.txt`.
