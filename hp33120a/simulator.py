"""Deterministic SCPI double, not a hardware-accuracy claim."""
from .protocol import execute
class Device:
    def __init__(self):
        self.writes=[]; self.queries=[]
        self.values={'*IDN?':'HEWLETT-PACKARD,33120A,SIMULATED,1.0','FUNC:SHAP?':'SIN','FREQ?':'1000',
            'VOLT?':'1','VOLT:OFFS?':'0','VOLT:UNIT?':'VPP','OUTP:LOAD?':'50','TRIG:SOUR?':'IMM',
            'FREQ:STAR?':'100','FREQ:STOP?':'1000','SWE:TIME?':'1','SWE:SPAC?':'LIN','PULS:DCYC?':'50','SYST:ERR?':'0,"No error"',**{m+':STAT?':'0' for m in ('AM','FM','BM','FSK','SWE')}}
    def query(self,command):
        self.queries.append(command)
        return self.values[command]
    def write(self,command):
        self.writes.append(command)
        if command.startswith('OUTP:LOAD '):
            load=command.split()[1]; new='50' if load=='50' else '9.9E+37'
            scale=1 if new==self.values['OUTP:LOAD?'] else 0.5 if new=='50' else 2
            for key in ('VOLT?','VOLT:OFFS?'): self.values[key]=str(float(self.values[key])*scale)
            self.values['OUTP:LOAD?']=new
        elif command=='VOLT:UNIT VPP': self.values['VOLT:UNIT?']='VPP'
        elif command.startswith('APPL:'):
            function,values=command[5:].split(); frequency,amplitude,offset=values.split(',')
            self.values.update({'FUNC:SHAP?':function,'FREQ?':frequency,'VOLT?':amplitude,'VOLT:OFFS?':offset,'TRIG:SOUR?':'IMM','FREQ:STAR?':'100','FREQ:STOP?':'1000','SWE:TIME?':'1','SWE:SPAC?':'LIN','PULS:DCYC?':'50'})
        elif command in ('SWE:STAT ON','SWE:STAT OFF'):
            self.values['SWE:STAT?']='1' if command.endswith('ON') else '0'
        elif command.split()[0] in ('FREQ:STAR','FREQ:STOP','SWE:TIME','SWE:SPAC'):
            key,value=command.split();self.values[key+'?']=value
        else: raise ValueError('Unsupported simulated command')
    def expected_voltage(self, physical_load):
        """Ideal 50-ohm source model for mismatch tests; not a measurement."""
        if physical_load not in ('50','INF'):raise ValueError('Model supports 50 ohms or open circuit')
        factor=(2 if self.values['OUTP:LOAD?']=='50' else 1)*(.5 if physical_load=='50' else 1)
        return {k:float(self.values[q])*factor for k,q in [('amplitude','VOLT?'),('offset','VOLT:OFFS?')]}
    def transport(self,target,action,**data):
        if target!='generator': raise ValueError('Wrong target')
        return execute(self,action,data)
