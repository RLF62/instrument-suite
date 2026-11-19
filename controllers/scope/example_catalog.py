"""Versioned built-in recipes. Separate from the user's presets.json."""
import copy
from scope_io import ScopeError

EXAMPLES = {
 'sony-elevator':{
  'id':'sony-elevator','name':'Sony CD changer — elevator control signals',
  'status':'Incomplete recipe','recallable':False,
  'purpose':'Observe the two CPU control signals associated with elevator motor M3 through IC505.',
  'connections':[{'channel':'CH1','point':'IC503 pin 38','role':'CPU control signal associated with M3 through IC505'},
                 {'channel':'CH2','point':'IC503 pin 37','role':'CPU control signal associated with M3 through IC505'}],
  'recorded':['CH1 at IC503 pin 38; CH2 at IC503 pin 37.',
              'Both channels DC coupled, approximately 2 V/div.',
              'These are CPU control signals, not motor-terminal measurements.'],
  'suggested':['For a newly completed recipe, use physical 10× probes and matching scope attenuation 10×. Earlier physical probe attenuation was not recorded.'],
  'missing':['Timebase','Trigger type, source, slope, level and mode'],
  'probe_notes':['Set both physical probe switches to 10× and the matching scope probe settings to 10× when completing this recipe.',
                 'Connect probe grounds only to a verified logic-ground reference. Confirm the board schematic before probing.',
                 'Do not move these probe tips to motor terminals; that would be a different measurement.'],
  'expected':['Look for CPU control levels/transitions associated with elevator operation.',
              'Exact voltage levels, timing and a complete direction/state table are not specified by this recipe.'],
  'limitations':['Exact timebase and trigger settings were not recorded. This recipe cannot be recalled until a working configuration is established and saved separately.',
                 'It is not an exact reproduction of the earlier session.'],
  'settings':{'ch1_on':'1','ch2_on':'1','ch1_coupling':'DC','ch2_coupling':'DC',
              'ch1_scale':'2','ch2_scale':'2','ch1_probe':'10','ch2_probe':'10'}
 },
 'sony-serial':{
  'id':'sony-serial','name':'Sony CD changer — serial activity',
  'status':'Suggested starting setup — not a verified capture','recallable':True,
  'purpose':'Look for serial clock and data activity at the CPU inputs during changer operation.',
  'connections':[{'channel':'CH1','point':'IC503 pin 24','role':'SCK input (explicit assignment for this suggested example)'},
                 {'channel':'CH2','point':'IC503 pin 26','role':'Serial data input (explicit assignment for this suggested example)'}],
  'recorded':['Reference notes identify pin 24 as SCK input and pin 26 as serial data input.',
              'Pin 2 is clock output; pin 3 is data output; pin 25 is not used.',
              'Those output pins are reference notes, not the probe points assigned by this example.'],
  'suggested':['CH1 → pin 24; CH2 → pin 26; trigger source CH1. These channel assignments are proposed explicitly for this example, not claimed as recorded earlier.',
               'Both channels DC coupled at 2 V/div; main timebase 1 ms/div.',
               'Edge trigger: CH1, falling edge, approximately 2.5 V, Auto mode.',
               'Physical 10× probes with matching scope attenuation 10×; prior-session attenuation was not recorded.'],
  'missing':[],
  'probe_notes':['Set both physical probe switches to 10× and both scope probe factors to 10× before using the suggested voltage settings.',
                 'CH1 tip goes to IC503 pin 24; CH2 tip goes to IC503 pin 26.',
                 'Connect probe grounds to a verified logic-ground reference. Confirm the pin locations on the correct board orientation.'],
  'expected':['Look for clock pulses and data-level changes while communication is active.',
              'Exact signal voltage, clock rate and burst timing were not recorded. The 2.5 V trigger is only a starting point; adjust it to the measured logic levels.'],
  'limitations':['This is a suggested starting setup, not a verified waveform capture or an exact recreation of the earlier session.',
                 'Only the listed settings are requested. Existing offset, position, bandwidth, invert and acquisition mode are not deliberately changed; probe-factor changes can rescale related values, so review readback.'],
  'settings':{'ch1_on':'1','ch2_on':'1','ch1_probe':'10','ch2_probe':'10',
              'ch1_coupling':'DC','ch2_coupling':'DC','ch1_scale':'2','ch2_scale':'2',
              'timebase':'0.001','trigger_type':'EDGE','trigger_source':'CH1',
              'trigger_slope':'FALL','trigger_level':'2.5','trigger_mode':'AUTO'}
 }
}
GENERAL_NOTES = [
 'Recalling a setup changes scope settings. It cannot move probe switches, attach ground clips or change wiring.',
 'Built-in examples are versioned separately from personal saved setups. Updates do not replace your personal presets.',
 'After checking wiring and testing a working configuration, save the scope readback under a new personal name.'
]
def example_by_id(ident):
    if not isinstance(ident,str) or ident not in EXAMPLES:
        raise ScopeError('Fischer Lab example not found.',404)
    return copy.deepcopy(EXAMPLES[ident])
def all_examples():
    return {'group':'Fischer Lab examples','notes':GENERAL_NOTES,'examples':copy.deepcopy(list(EXAMPLES.values()))}
