import bluesky.plans as bp
import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import bluesky.callbacks.fitting
import numpy as np
import pandas as pd
import lmfit
from bluesky.callbacks import LiveFit
from bluesky.suspenders import SuspendFloor
from ophyd import EpicsSignal
from tabulate import tabulate

# tm1sum = EpicsSignal('XF:10ID-BI:TM176:SumAll:MeanValue_RBV')
# susp = SuspendFloor(tm1sum, 1.e-5, resume_thresh = 1.e-5, sleep = 1*60)

# uofb_pv = EpicsSignal("SR:UOFB{}ConfigMode-I", name="uofb_pv")
# id_bump_pv = EpicsSignal("SR:UOFB{C10-ID}Enabled-I", name="id_bump_pv")
# nudge_pv = EpicsSignal("SR:UOFB{C10-ID}Nudge-Enabled", name="nudge_pv")

def align_with_fit(dets, mtr, start, stop, gaps, mode='rel', md=None):
    # Performs relative scan of motor and retuns data staistics

    md = md or {}
    plt.cla()

    local_peaks = []
    for det in dets:
        for hint in det.hints['fields']:
            local_peaks.append(
                bluesky.callbacks.fitting.PeakStats(mtr.hints['fields'][0], hint)
            ) 
    # TODO use relative wrapper to avoid the reset behavior (or make it optional)
    
    if mode == 'rel':
        plan = bpp.subs_wrapper(
            bp.rel_scan(dets, mtr, start, stop, gaps+1, md=md), 
            local_peaks
            )
    else:
        plan = bpp.subs_wrapper(
            bp.scan(dets, mtr, start, stop, gaps+1, md=md), 
            local_peaks
            )
    yield from plan
    return local_peaks

#def set_lambda_exposure(exposure):
#    det = lambda_det
#    yield from bps.mv(det.cam.acquire_time, exposure, det.cam.acquire_period, exposure)

def check_zero(dets=[lambda_det], start=-20, stop=20, gaps=200, exp_time=1, md=None):
    # Performs relative scan of the HRM energy at tth = 0 and positions it to the peak center

    #
    print('scanning zero')
    #
    md = md or {}
    yield from bps.mv(spec.tth, 0)
    sample_pos = yield from bps.read(sample_stage)
    print(sample_pos)
#    if dets is None:
#        dets = [lambda_det]

    yield from set_lambda_exposure(exp_time)
    yield from bps.mv(whl, 7)
    for d in dets:
        # set the exposure times
        pass

    local_peaks = yield from align_with_fit(dets, hrmE, start, stop, gaps, 'rel', md)
    cen = local_peaks[0].cen

    peak_stats = bec.peaks
    peaks_stats_print('lambda_det_stats7_total', peak_stats)

    if cen is not None:
        target = 0.2 * round(cen/0.2)
        # move too far for backlash compensation
        yield from bps.mv(hrmE, target - 20)
        # apporach target from negative side 
        yield from bps.mv(hrmE, target)
        print('\n')
        print(f"HRM energy is set to E = {hrmE.energy.read()['hrmE']['value']}\n")

def do_the_right_thing(i_time):
    yield from bps.mv(det1.integration_time, i_time)
    yield from count([det1])

def ct(exp_time):
    yield from bps.mv(sclr.preset_time, exp_time)
    yield from bp.count([sclr])


def double_ct(exp_time):
    yield from ct(exp_time)
    # yield from bps.mv(sample_stage.sx, 0)
    yield from ct(exp_time)

def Lipid_Qscan(Qq=None, Ncycles=1, md=None):
    # Test plan for the energy scan at several Q values
    # Usage: 
    md = md or {}
    tth001 = 16.8
#    Qq = [1, 2, 3]
    c22 = sclr.channels.chan22
    yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
    yield from bps.mv(mcm_slits.inboard, -1, mcm_slits.outboard, 1)

    for kk in range(Ncycles):
        yield from bps.mv(anapd, 25)
        #yield from set_lambda_exposure(2)
        yield from check_zero(start=-5, stop=5, gaps=40, exp_time=1)
        yield from bps.mv(whl, 0)
        if Qq == None:
            print('\n')
            print('Empty Q-list. Scan is finished.\n')
            return
        else:
            for q in Qq:
                print(f"Starting energy scan at Q = {q} nm-1\n")
                plt.cla()
                th = qq2th(q)
                yield from bps.mv(spec.tth, th)
                yield from hrmE_dscan(-5, 5, 10, 2, md=md)

#                yield from bps.mvr(sample_stage.sx, 0.03)
                print(f"Moving the TTH to the Tth = {tth001} angle\n")
                yield from bps.mv(spec.tth, tth001)
                yield from set_lambda_exposure(5)

                print("Scanning the sample SSY\n")
                yield from bp.rel_scan([lambda_det], sample_stage.sy, -0.1, 0.1, 40, md=md)
                max_pos = peaks['max'][lambda_det_stats7_total][0]
                peaks_stats_print('lambda_det_stats7_total', peaks)
#                peak_stats = bec.peaks
#                max_pos = peak_stats['max']['lambda_det_stats7_total'][0]

                yield from bps.mvr(sample_stage.sy, -0.1)
                yield from bps.mv(sample_stage.sy, max_pos)
                print(f"Sample stage SY is set to {sample_stage.sy.read()['s_sy']['value']}\n")

                print("Scanning the sample SSZ\n")
                yield from bp.scan([lambda_det], sample_stage.sz, -2, 2, 40, md=md)
                max_pos = peaks['max'][lambda_det_stats7_total][0]
                peaks_stats_print('lambda_det_stats7_total', peaks)
#                peak_stats = bec.peaks
#                max_pos = peak_stats['max']['lambda_det_stats7_total'][0]

                yield from bps.mv(sample_stage.sz, max_pos)
                print(f"Sample stage SZ is set to {sample_stage.sz.read()['s_sz']['value']}\n")

                print("Scanning the sample SSY\n")
                yield from bp.rel_scan([lambda_det], sample_stage.sy, -0.1, 0.1, 40, md=md)
                max_pos = peaks['max'][lambda_det_stats7_total][0]
                peaks_stats_print('lambda_det_stats7_total', peaks)
#                peak_stats = bec.peaks
#                max_pos = peak_stats['max']['lambda_det_stats7_total'][0]

                yield from bps.mvr(sample_stage.sy, -0.1)
                yield from bps.mv(sample_stage.sy, max_pos)
                print(f"Sample stage SY is set to {sample_stage.sy.read()['s_sy']['value']}\n")

#        yield from bps.mv(anapd, 3, spec.tth, 1)
#        yield from bps.mv(sclr.channels.chan22.preset_time, 5)
#        yield from bp.scan([c22], spec.tth, 1, 21, 101, md=md)

def Lipid_Qscan_wBC():
    # Lipid_Qscan with beam check
    yield from bpp.suspend_wrapper(Lipid_Qscan(), susp)


def Peak_Test(det, mot, det_channel_picks=[]):
    # yield from bp.rel_scan([det1], ixs4c.omega, -5, 5, 5)
    # plan = bpp.subs_wrapper(
    #      bp.rel_scan([det1], ixs4c.omega, -5, 5, 5), 
    #      LivePlot(det1.hints['fields'][0], ixs4c.omega.name)
    #         )
#    if not plt.fignum_exists(1):
#        plt.subplots(figsize=(8,5), num=1)
#    else:
    plt.cla()
    
    if len(det_channel_picks) == 0:
#        plan = bp.rel_scan([det], ixs4c.omega, -5, 5, 5)
#        subs_list = [plotselect(det.hints['fields'], mot.name)]
#        stats_list = [PeakStats(mot.name, det.hints['fields'])]
        subs_list = [LivePlot(det.hints['fields'][0], x=mot.name, marker='*', markersize=10, ax=myaxs)]
        stats_list = [PeakStats(mot.name, det.hints['fields'][0])]
    else:
#        local_peaks = []
#        for det in dets:
#        subs_list = [LivePlot(det.hints['fields'][det_channel], mot.name, ax=plt.gca()) for det_channel in  det_channel_picks]
        subs_list = [plotselect(det.hints['fields'][det_channel], mot.name) for det_channel in  det_channel_picks]
        stats_list = [PeakStats(mot.name, det.hints['fields'][det_channel]) for det_channel in det_channel_picks]

    subs_list.extend(stats_list)
    plan = bpp.subs_wrapper(
             bp.rel_scan([det], ixs4c.omega, -5, 5, 5), subs_list)
        
    yield from plan
    if len(det_channel_picks) > 0:
        for n in range(len(det_channel_picks)):
            peaks_stats_print(det.hints['fields'][det_channel_picks[n]], stats_list[n])
            print("\n")

#    print(stats_list)
#     local_peaks = yield from align_with_fit([det1], ixs4c.omega, -5, 5, 5, LivePlot())
#    return stats_list
