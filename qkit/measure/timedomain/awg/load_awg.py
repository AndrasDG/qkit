import qt
import numpy as np
import os.path
import time
import logging
import numpy
import sys
from qkit.gui.notebook.Progress_Bar import Progress_Bar
import gc


def update_sequence(ts, wfm_func, sample, iq = None, loop = False, drive = 'c:', path = '\\waveforms', reset = True, marker=None, markerfunc=None, ch2_amp = 2):
	'''
		set awg to sequence mode and push a number of waveforms into the sequencer
		
		inputs:
		
		ts: array of times, len(ts) = #sequenzes
		wfm_func: waveform function usually generated via generate_waveform using ts[i]; this can be a touple of arrays (for channels 0,1, heterodyne mode) or a single array (homodyne mode)
		sample: sample object
		
		iq: Reference to iq mixer instrument. If None (default), the wfm will not be changed. Otherwise, the wfm will be converted via iq.convert()
		
		marker: marker array in the form [[ch1m1,ch1m2],[ch2m1,ch2m2]] and all entries arrays of sample length
		markerfunc: analog to wfm_func, set marker to None when used
		
		for the 6GS/s AWG, the waveform length must be divisible by 64
		for the 1.2GS/s AWG, it must be divisible by 4
	'''
	qt.mstart()
	awg = sample.get_awg()
	clock = sample.get_clock()
	wfm_func2 = wfm_func
	if iq != None:
		wfm_func2 = lambda t, sample: iq.convert(wfm_func(t,sample))
	
	# create new sequence
	if reset:
		if "Tektronix" in awg.get_type():
			awg.set_runmode('SEQ')
			awg.set_seq_length(0)   #clear sequence, necessary?
		elif "Tabor" in awg.get_type():
			awg.set_p1_runmode('SEQ')
		
		awg.set_seq_length(len(ts))   #create empty sequence
		
		#amplitude settings of analog output
		awg.set_ch1_offset(0)
		awg.set_ch2_offset(0)
		awg.set_ch1_amplitude(2)
		awg.set_ch2_amplitude(ch2_amp)

	#generate empty tuples
	wfm_samples_prev = [None,None]
	wfm_fn = [None,None]
	wfm_pn = [None,None]
	p = Progress_Bar(len(ts)*(2 if "Tektronix" in awg.get_type() else 1),'Load AWG')   #init progress bar
	
	#update all channels and times
	for ti, t in enumerate(ts):   #run through all sequences
		qt.msleep()
		wfm_samples = wfm_func2(t,sample)   #generate waveform
		if not isinstance(wfm_samples[0],(list, tuple, np.ndarray)):   #homodyne
			wfm_samples = [wfm_samples,np.zeros_like(wfm_samples, dtype=np.int8)]
		
		for chan in [0,1]:
			if markerfunc != None:   #use markerfunc
				try:
					if markerfunc[chan][0] == None:
						marker1 = np.zeros_like(wfm_samples, dtype=np.int8)[0]
					else:
						marker1 = markerfunc[chan][0](t,sample)
					
					if markerfunc[chan][1] == None:
						marker2 = np.zeros_like(wfm_samples, dtype=np.int8)[0]
					else:
						marker2 = markerfunc[chan][1](t,sample)
				
				except TypeError:   #only one markerfunc given
					marker1, marker2 = np.zeros_like(wfm_samples, dtype=np.int8)
					if chan == 0:
						marker1 = markerfunc(t,sample)
					
			elif marker == None:   #fill up with zeros
				marker1, marker2 = np.zeros_like(wfm_samples, dtype=np.int8)
			else: #or set your own markers
				c_marker1, c_marker2 = marker[chan]
				marker1 = c_marker1[ti]
				marker2 = c_marker2[ti]
			
			if "Tektronix" in awg.get_type():
				wfm_fn[chan] = 'ch%d_t%05d'%(chan+1, ti) # filename is kept until changed
				if len(wfm_samples) == 1 and chan == 1:
					wfm_pn[chan] = '%s%s\\%s'%(drive, path, np.zeros_like(wfm_fn[0]))   #create empty array
				else:
					wfm_pn[chan] = '%s%s\\%s'%(drive, path, wfm_fn[chan])
				awg.wfm_send(wfm_samples[chan], marker1, marker2, wfm_pn[chan], clock)
				
				awg.wfm_import(wfm_fn[chan], wfm_pn[chan], 'WFM')
				
				# assign waveform to channel/time slot
				awg.wfm_assign(chan+1, ti+1, wfm_fn[chan])
				
				if loop:
					awg.set_seq_loop(ti+1, np.infty)
			elif "Tabor" in awg.get_type():
				if chan == 0:
					awg.wfm_send2(wfm_samples[0],wfm_samples[1],marker1,marker2,chan+1,ti+1)
				else: continue
			else:
				raise ValueError("AWG type not known")
			p.iterate()

		gc.collect()

	if reset and "Tektronix" in awg.get_type():
		# enable channels
		awg.set_ch1_status(True)
		awg.set_ch2_status(True)
		awg.set_seq_goto(len(ts), 1)
		awg.run()
		awg.wait(10,False)
	elif reset and "Tabor" in awg.get_type():
		# enable channels
		#awg.preset()
		awg.set_ch1_status(True)
		awg.set_ch2_status(True)
	qt.mend()
	return np.all([awg.get('ch%i_status'%i) for i in [1,2]])
