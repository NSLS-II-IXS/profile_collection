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

tm1sum = EpicsSignal('XF:10ID-BI:TM176:SumAll:MeanValue_RBV')
susp = SuspendFloor(tm1sum, 1.e-5, resume_thresh = 1.e-5, sleep = 1*60)

uofb_pv = EpicsSignal("SR:UOFB{}ConfigMode-I", name="uofb_pv")
id_bump_pv = EpicsSignal("SR:UOFB{C10-ID}Enabled-I", name="id_bump_pv")
nudge_pv = EpicsSignal("SR:UOFB{C10-ID}Nudge-Enabled", name="nudge_pv")

Dtemp1 = EpicsSignal("XF:10ID-CT{FbPid:01}PID.VAL", name="Dtemp1")
Dtemp2 = EpicsSignal("XF:10ID-CT{FbPid:02}PID.VAL", name="Dtemp2")
Dtemp3 = EpicsSignal("XF:10ID-CT{FbPid:03}PID.VAL", name="Dtemp3")
Dtemp4 = EpicsSignal("XF:10ID-CT{FbPid:04}PID.VAL", name="Dtemp4")
Dtemp5 = EpicsSignal("XF:10ID-CT{FbPid:05}PID.VAL", name="Dtemp5")
Dtemp6 = EpicsSignal("XF:10ID-CT{FbPid:06}PID.VAL", name="Dtemp6")

airpad = EpicsSignal("XF:10IDD-CT{IOC-MC:12}AirOn-cmd", name="airpad")
det2range = EpicsSignal("XF10ID-BI:AH172:Range", name="det2range")


def gaussian(x, A, sigma, x0):
    return A*np.exp(-(x - x0)**2/(2 * sigma**2))

def stepup(x, A, sigma, x0):
    return A*(1-1/(1+np.exp((x-x0)/sigma)))

def stepdown(x, A, sigma, x0):
    return A*(1-1/(1+np.exp(-(x-x0)/sigma)))

def calc_lmfit(uid=-1, x="hrmE", channel=7):
    # Calculates fitting parameters for Gaussian function for energy scan with UID and Lambda channel
    hdr = db[uid]
    table = hdr.table()
    model = lmfit.Model(gaussian)
    y = f'lambda_det_stats{channel}_total'
    lf = LiveFit(model, y, {'x': x}, {'A': table[y].max(), 'sigma': 0.7, 'x0': table[x][table[y].argmax()+1]})
    for name, doc in hdr.documents():
        lf(name, doc)
    gauss = gaussian(table[x], **lf.result.values)
    plt.plot(table[x], table[y], label=f"raw, channel={channel}", marker = 'o', linestyle = 'none')
    plt.plot(table[x], gauss.values, label=f"gaussian fit {channel}")
    plt.legend()
    return lf.result.values

def calc_stepup_fit(x):
    # Calculates fitting parameters for step up function for MCM slits scan
    hdr = db[-1]
    table = hdr.table()
    model = lmfit.Model(stepup)
    y = 'det2_current1_mean_value'
    lf = LiveFit(model, y, {'x': x}, {'A': table[y].max(), 'sigma': 0.25, 'x0': 0})
    for name, doc in hdr.documents():
        lf(name, doc)
    print(lf.result.values)
    stup = stepup(table[x], **lf.result.values)
    plt.clf()
    plt.plot(table[x], table[y], label=f"raw data", marker = 'o', linestyle = 'none')
    plt.plot(table[x], stup.values, label=f"data fit")
    plt.legend()
    return lf.result.values['x0']

def calc_stepdwn_fit(x):
    # Calculates fitting parameters for step down function for MCM slits scan
    hdr = db[-1]
    table = hdr.table()
    model = lmfit.Model(stepdown)
    y = 'det2_current1_mean_value'
    lf = LiveFit(model, y, {'x': x}, {'A': table[y].max(), 'sigma': 0.25, 'x0': 0})
    for name, doc in hdr.documents():
        lf(name, doc)
    print(lf.result.values)
    stdw = stepdown(table[x], **lf.result.values)
    plt.clf()
    plt.plot(table[x], table[y], label=f"raw data", marker = 'o', linestyle = 'none')
    plt.plot(table[x], stdw.values, label=f"data fit")
    plt.legend()
    return lf.result.values['x0']

def GCarbon_Qscan(exp_time=2):
    # Test plan for the energy resolution at Q=1.2 with the Glassy Carbon
    Qq = [1.2]
    yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
    yield from bps.mv(anapd, 25, whl, 0)
    plt.clf()

    for kk in range(1):
        for q in Qq:
            th = qq2th(q)
            yield from bps.mv(spec.tth, th)
            yield from hrmE_dscan(-10, 10, 100, exp_time)


def DxtalTempCalc(uid=-1):
    # Calculates temperature correction for the D crystals
    E0 = 9131.7     # energy (eV)
    TH = 88.5       # Dxtal asymmetry angle (deg)
    C1 = 3.725e-6   # constant (1/K)
    C2 = 5.88e-3    # constant (1/K)
    C3 = 5.548e-10  # constant (1/K2)
    T1 = 124.0      # temperature (K)
    T0 = 300.15     # crystal average temperature (K)

    bet = C1*(1 - np.exp(-C2*(T0-T1))) + C3*T0
    dE = []
    plt.clf()
    for n in range(1,7):
        fit_par = calc_lmfit(uid, channel=n)
        if fit_par['A'] < 100:
            print('**********************************')
            print('         WARNING !')
            print('      Fitting Error')
            return
        
        dE.append(fit_par['x0'])

    dE = [x-dE[0] for x in dE]
    dTe = [1.e-3*x/E0/bet for x in dE]
    dTh = [1.e3*x*np.tan(np.radians(TH))/E0 for x in dE]
    
    DTe = [Dtemp1.read()['Dtemp1']['value']+dTe[0], 
           Dtemp2.read()['Dtemp2']['value']+dTe[1], 
           Dtemp3.read()['Dtemp3']['value']+dTe[2], 
           Dtemp4.read()['Dtemp4']['value']+dTe[3], 
           Dtemp5.read()['Dtemp5']['value']+dTe[4], 
           Dtemp6.read()['Dtemp6']['value']+dTe[5]]
    Dheader = [' ', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6']
    dE.insert(0,'dEnrg')
    dTe.insert(0,'dTemp')
    dTh.insert(0,'dThe')
    DTe.insert(0,'Dtemp')
    Ddata = [dE, dTh, dTe, DTe]
    print('---------------------------------------------------------------------')
    print(tabulate(Ddata, headers=Dheader, tablefmt='pipe', stralign='center', floatfmt='.4f'))
    print('---------------------------------------------------------------------\n')
    update_temp = input('Do you want to update the temperature (yes/no): ')
    if update_temp == 'yes':
        d1 = Dtemp1.set(DTe[1])
        d2 = Dtemp2.set(DTe[2])
        d3 = Dtemp3.set(DTe[3])
        d4 = Dtemp4.set(DTe[4])
        d5 = Dtemp5.set(DTe[5])
        d6 = Dtemp6.set(DTe[6])
        # wait(d1, d2, d3, d4, d5, d6)
        print('\n')
        print('The temperature is updated')
    else:
        print('\n')
        print('Update is canceled')
    return {'dEn':dE, 'dTem':dTe, 'dThe':dTh, 'DTem':DTe}

def ura_setup_prep():
# Prepares the URA for the MCM and Analyzer Slits setup, namely opens the Slits and lowers the analyzer
    hux = hrm2.read()['hrm2_ux']['value']
    hdx = hrm2.read()['hrm2_ux']['value']
    if hux > -5 or hdx > -5:
        print('*************************************\n')
        print('HRM is in the beam. Execution aborted')
        return
    d1 = airpad.set(1)
    d2 = det2range.set(0)
 
    yield from bps.mv(spec.tth, 0)
    acyy = anc_xtal.y.read()['anc_xtal_y']['value']

    yield from bps.mv(anc_xtal.y, 0.5, whl, 2, anpd, 0)
    yield from bps.mv(analyzer_slits.top, 2, analyzer_slits.bottom, -2, analyzer_slits.outboard, 2, analyzer_slits.inboard, -2)
    d21cnt = det2.current1.mean_value.read()['det2_current1_mean_value']['value']
    if d21cnt < 1.0e5:
        print('*************************************\n')
        print('Low intensity on D21. Execution aborted')
        yield from bps.mv(anc_xtal.y, acyy, anpd, -90)
        return
    return acyy

def ura_setup_post(y0):
# Returns the motors to thier previous positions after the MCM and Analyzer Slits setup
    yield from bps.mv(anc_xtal.y, y0, whl, 0, anpd, -90)
    yield from bps.mv(analyzer_slits.top, 1, analyzer_slits.bottom, -1, analyzer_slits.outboard, 1.5, analyzer_slits.inboard, -1.5)
    return


def mcm_setup(s1=0, s2=0):
# MCM mirror setup procedure
# Usage:
#       if s1 > 0, then execute mcmx alignment, else - skip it
#       if s2 > 0, then execute mcmy alignment, else - skip it
    MCM_XPOS = -0.941
    if s1 == 0 and s2 == 0:
        print('*************************************\n')
        print('Usage: mcm_setup(s1,s2)')
        print('if s1 > 0, then execute mcmx alignment, else - skip it')
        print('if s2 > 0, then execute mcmy alignment, else - skip it')
        return
    acyy = ura_setup_prep()
    if not s1 == 0:
        yield from bp.rel_scan([det2], mcm.x, -0.2, 0.2, 41)
        x_pos = calculate_max_value(uid=-1, x="mcm.x", y="det2_current1_mean_value", delta=1, sampling=100)
        xmax = x_pos[0]
        dxmax = MCM_XPOS - xmax
        print(f"Maximum position X = {xmax}. Shifted by {dxmax} from the target")
        kc = 1
        while abs(dxmax) > 1.0e-3:
            yield from bps.mvr(sample_stage.tx, dxmax)
            yield from bp.rel_scan([det2], mcm.x, -0.2, 0.2, 41)
            x_pos = calculate_max_value(uid=-1, x="mcm.x", y="det2_current1_mean_value", delta=1, sampling=100)
            xmax = x_pos[0]
            dxmax = MCM_XPOS - xmax
            print(f"Maximum position X = {xmax}. Shifted by {dxmax} from the target")
            kc += 1
            if kc > 5:
                print("Could not set the MCM_X to maximum. Execution aborted")
                ura_setup_post(acyy)
                break

def san_setup():
    acyy = ura_setup_prep()
    yield from bps.mv(analyzer_slits.outboard, 0)
    yield from bp.rel_scan([det2], analyzer_slits.outboard, -1.2, 1.2, 41)
    x0 = calc_stepup_fit('analyzer_slits_outboard')
    if x0 > 1 or x0 < -1:
        print('*********************************************************\n')
        print('Verify the analyzer slits outboard data. Execution aborted!')
    
    yield from bps.mv(analyzer_slits.outboard, 2, analyzer_slits.inboard, 0)
    yield from bp.rel_scan([det2], analyzer_slits.inboard, -1.2, 1.2, 41)
    x0 = calc_stepdwn_fit('analyzer_slits_inboard')
    if x0 > 1 or x0 < -1:
        print('********************************************************\n')
        print('Verify the analyzer slits inboard data. Execution aborted!')
    
    yield from bps.mv(analyzer_slits.inboard, -2, analyzer_slits.top, 0)
    yield from bp.rel_scan([det2], analyzer_slits.top, -1., 1., 41)
    x0 = calc_stepup_fit('analyzer_slits_top')
    if x0 > 1 or x0 < -1:
        print('********************************************************\n')
        print('Verify the analyzer slits top data. Execution aborted!')
    
    yield from bps.mv(analyzer_slits.top, 2, analyzer_slits.bottom, 0)
    yield from bp.rel_scan([det2], analyzer_slits.bottom, -1., 1., 41)
    x0 = calc_stepdwn_fit('analyzer_slits_bottom')
    if x0 > 1 or x0 < -1:
        print('********************************************************\n')
        print('Verify the analyzer slits bottom data. Execution aborted!')
    
    ura_setup_post(acyy)
    print('*****************************************\n')
    print("Analyzer slits setup finished successfully")

def calculate_max_value(uid=-1, x="hrmE", y="lambda_det_stats7_total", delta=1, sampling=200):
    """
    This method gets a table (DataFrame) by using its uid. it finds the maximum value of the curve 
    under the sampled data by using the maximum y value and its neighboring data samples and then, 
    applying a polynomial regression over this curve. The model is used as an interpolation approach
    to generate more points between the original range and to return the x and y values of the
    maximum point of this new model

    Parameters
    ----------
    uid : int, optional
        id of the scan. The default is -1.
    x : str, optional
        label of the x values in the table. The default is "hrmE".
    channel : str, optional
        value of the channel with the y values. The default is 7.
    delta : int, optional
        total of points to be used on each side of the maximum value to generate the new model. The default is 1.
    sampling : int, optional
        total of sampling points to be used for interpolation. The default is 200.

    Raises
    ------
    ValueError
        The selected delta value is too big to be used based on the position of the maximum value in the table.

    Returns
    -------
    flaot
        x value of the maximum value.
    float
        y value of the maximum value.

    """
    
    
    hdr = db[uid]
    table = hdr.table()
    #y = f'lambda_det_stats{channel}_total'
    
    #cp_df = df.copy()
    
    max_id = table[y].idxmax()
    
    # low limit check
    if max_id >= delta:
        low_max_id = max_id - delta
    else:
        raise ValueError("Delta value is greater than the lower limit of the dataset")
    
    # high limit check
    if max_id < len(table[y])-delta-1:
        high_max_id = max_id + delta + 1
    else:
        raise ValueError("Delta value is greater than the upper limit of the dataset")
    
    y_values = table[y][low_max_id:high_max_id]
    x_values = table[x][low_max_id:high_max_id]
    
    model = np.poly1d(np.polyfit(x_values, y_values, 2))
    
    resampled_x_values = np.linspace(x_values.iloc[0],x_values.iloc[-1],sampling)
    resampled_y_values = model(resampled_x_values)
    
    resample_df = pd.DataFrame({x:resampled_x_values, y:resampled_y_values})
    
    new_max_id = resample_df[y].idxmax()
    
    return resample_df[x][new_max_id], resample_df[y][new_max_id]


def LocalBumpSetup():
#   Adjusts the e-beam local bump
#
#    uofb_pv = EpicsSignal("SR:UOFB{}ConfigMode-I", name="uofb_pv")
#    id_bump_pv = EpicsSignal("SR:UOFB{C10-ID}Enabled-I", name="id_bump_pv")
#    nudge_pv = EpicsSignal("SR:UOFB{C10-ID}Nudge-Enabled", name="nudge_pv")
    cond1 = uofb_pv.read()['uofb_pv']['value']
    cond2 = id_bump_pv.read()['id_bump_pv']['value']
    cond3 = nudge_pv.read()['nudge_pv']['value']
    if cond1 != 2:
        print("****************** WARNING ******************")
        print("The UOFB is disabled. Operation is terminated")
        return
    if cond2 != 1:
        print("****************** WARNING ******************")
        print("The ID Bump is disabled. Operation is terminated")
        return
    if cond3 != 1:
        print("****************** WARNING ******************")
        print("The Nudge is disabled. Operation is terminated")
        return
