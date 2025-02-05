import matplotlib as mpl
import matplotlib.pyplot as plt
import multiprocessing as multi
import numpy as np
import os 
import pandas as pd
import pmagpy
import pmagpy.ipmag as ipmag
import pmagpy.pmag as pmag
import pmagpy.pmagplotlib as pmagplotlib
import re
import scipy.integrate as integrate
import scipy.stats as stats
import seaborn as sns
import SPD.lib.leastsq_jacobian as lib_k
import sys

from datetime import datetime as dt
from importlib import reload
from multiprocessing import Pool
from scipy.stats import linregress



def API_param_combine(sid_df,afnrm,aftrm1,trm1_star_min,minN):
    #
    ## calculating first heating parameters
    ntrmRegs1=[]
    #
    used_df=sid_df[sid_df.treat>=trm1_star_min]
    used_df=used_df[['treat','nrm','trm1_star']]
    trm1_star_max=used_df['treat'].tolist()[len(used_df)-1]
    variables = []
    for i in range(len(used_df)-minN+1):
        for j in range(len(used_df)-minN+1-i):
            variables = variables + [[used_df, afnrm,\
                                        used_df['treat'].tolist()[i],\
                                        used_df['treat'].tolist()[i+j+minN-1],'trm1_star','nrm']]
    p=Pool(multi.cpu_count())
    ntrmRegs1=pd.DataFrame(p.map(wrapper_ltd_pars_mod, variables))
    ntrmRegs1.columns=['n_n','slope_n','r_n','dAIC_n','frac_n',\
                       'step_min_n','step_max','beta_n','krv_n','krvd_n','f_resid_n']
    p.close()
    p.terminate()
    print('[calculated for', len(ntrmRegs1),\
          'step-combinations for 1st heating parameters',\
          '(', trm1_star_min, '-', trm1_star_max, 'mT)]')
    #print(ntrmRegs1)
    #
    ## calculating second heating parameters
    trmRegs1=[]
    # interval serach from ZERO up to MAX
    trm2_star_min=sid_df['treat'].tolist()[0]
    used_df=sid_df[sid_df.treat>=trm2_star_min]
    used_df=used_df[['treat','trm1','trm2_star']]
    trm2_star_max=used_df['treat'].tolist()[len(used_df)-1]
    variables = []
    for i in range(len(used_df)-minN+1):
        for j in range(len(used_df)-minN+1-i):
            variables = variables + [[used_df, aftrm1,\
                                        used_df['treat'].tolist()[i],\
                                        used_df['treat'].tolist()[i+j+minN-1],'trm2_star','trm1']]
    p=Pool(multi.cpu_count())
    trmRegs1=pd.DataFrame(p.map(wrapper_ltd_pars_mod, variables))
    trmRegs1.columns=['n_t','slope_t','r_t','dAIC_t','frac_t',\
                      'step_min_t','step_max','beta_t','krv_t','krvd_t','f_resid_t']
    p.close()
    p.terminate()
    print('[calculated for', len(trmRegs1),\
          'step-combinations for 2nd heating parameters',\
          '(', trm2_star_min, '-', trm2_star_max, 'mT)]')
    #print(trmRegs1)
    #
    print('[merge the combinations for H_min_n >= H_min_t with common H_max]')
    combinedRegs0=[]
    combinedRegs0=pd.merge(ntrmRegs1, trmRegs1, on='step_max', how='outer')
    combinedRegs1=[]
    combinedRegs1=combinedRegs0[combinedRegs0.step_min_n>=combinedRegs0.step_min_t]
    print(' ', len(combinedRegs0), ' cominbnations --> ',\
              len(combinedRegs1), ' cominbnations')
    #print(combinedRegs1)
    #    
    ## calculating dAPI(difference between resultantAPI/expectedAPI)
    #aftrm10=sid_data[sid_data.description.str.contains('TRM10')] # set lab_field
    #if (len(aftrm10)>0): lab_field=aftrm10.treat_dc_field.tolist()[0]
    #combinedRegs1['dAPI']=abs(1 - combinedRegs1['slope_n'] * lab_field / True_API)
    #print(combinedRegs1)
    #screened=combinedRegs1
    #
    return combinedRegs1



def clean_duplicates(df,type):
    clean_df=df[ ((df['step']==0)  &(df.XRM==type) )==False]
    duplicate=df[ ((df['step']==0)  &(df.XRM==type) )==True].tail(1)
    df=pd.concat((clean_df,duplicate))
    df.sort_values(by='number',inplace=True)
    return df



def convert_ts_dspin(infile, citations, instrument, ARM_DC_field):
    #
    info=pd.read_csv(infile,nrows=4,header=None)[0]
    weightline=info.loc[info.str.contains('weight')==True]
    #weight_gm=float(weightline.str.split().values[-1][-1][:-1])
    weight_gm=float(re.findall("\d+\.\d+", str(weightline))[0])
    IDline=info.loc[info.str.contains('\$')==True].str.split().values[-1]
    specimen,azimuth,dip,lab_field_uT=IDline[1],float(IDline[2]),float(IDline[3]),float(IDline[4])
    site=specimen.split('-')[0]
    sample=site+'-'+specimen.split('-')[1]
    #
    columns=['XRM','step','magn_mass','dir_inc','dir_dec','Smag']
    lab_field=lab_field_uT*1e-6 # convert from uT to T
    data=pd.read_csv(infile,delim_whitespace=True,header=None,skiprows=4)
    data.columns=columns
    data['dir_dec']=data['dir_dec']%360
    data=data[data.XRM.str.contains('#')==False]
    #
    # set some defaults
    data['description']=""
    data['specimen']=specimen
    data['sample']=sample # assume specimen=sample
    data['site']=site                                                         
    data['weight'],weight=weight_gm*1e-3,weight_gm*1e-3 # use weight in kg
    data['azimuth']=azimuth
    data['dip']=dip
    data['treat_temp']=273.
    data['treat_ac_field']=data['step']*1e-3 # convert mT to T
    data['treat_dc_field']=0
    data['treat_dc_field_phi']=""
    data['treat_dc_field_theta']=""
    data['meas_temp']=273.
    data['citations']=citations
    data['software_packages'],version=pmag.get_version(),pmag.get_version()
    data['instrument_codes']=instrument
    data['standard']='u' # set to unknown 
    data['quality']='g' # set to good as default
    methstring='LP-PI-TRM:LP-PI-ALT-AFARM:LP-LT'
    data['method_codes']=methstring
    #
    data=data[((data['step']!=0) & (data.XRM=='ARM00'))==False] # delete all but first ARM00
    data=data[((data['step']!=0) & (data.XRM=='ARM10'))==False] # delete all but first ARM10
    data=data[((data['step']!=0) & (data.XRM=='ARM20'))==False] # delete all but first ARM20
    ## delete the extra step 0 steps for ARM0,  ARM1 & ARM2
    data['number'] = range(len(data))
    #
    data=clean_duplicates(data,'ARM0')
    data=clean_duplicates(data,'ARM1')
    data=clean_duplicates(data,'ARM2')
    data=clean_duplicates(data,'TRM10')
    # add descriptions for plotting
    data.loc[(data.XRM.str.contains('NRM')==True),'description']='NRM'
    data.loc[(data.XRM.str.contains('NRM0')==True),'description']='NRM0'
    data.loc[(data.XRM.str.contains('ARM0')==True),'description']='ARM0'
    data.loc[(data.XRM.str.contains('ARM00')==True),'description']='ARM00'
    data.loc[(data.XRM.str.contains('TRM1')==True),'description']='TRM1'
    data.loc[(data.XRM.str.contains('TRM10')==True),'description']='TRM10'
    data.loc[(data.XRM.str.contains('ARM1')==True),'description']='ARM1'
    data.loc[(data.XRM.str.contains('ARM10')==True),'description']='ARM10'
    data.loc[(data.XRM.str.contains('TRM2')==True),'description']='TRM2'
    data.loc[(data.XRM.str.contains('TRM20')==True),'description']='TRM20'
    data.loc[(data.XRM.str.contains('ARM2')==True),'description']='ARM2'
    data.loc[(data.XRM.str.contains('ARM20')==True),'description']='ARM20'
    #
    ARM0_step=data[ (data.XRM.str.contains('ARM0')==True)].head(1)
    if (len(ARM0_step)>0):
        ARM0_phi=ARM0_step['dir_dec'].values[0]
        ARM0_theta=ARM0_step['dir_inc'].values[0]
    #
    TRM1_step=data[ (data.XRM.str.contains('TRM1')==True)].head(1)
    if (len(TRM1_step)>0):
        TRM1_phi=TRM1_step['dir_dec'].values[0]
        TRM1_theta=TRM1_step['dir_inc'].values[0]
    #
    ARM1_step=data[ (data.XRM.str.contains('ARM1')==True)].head(1)
    if (len(ARM1_step)>0):
        ARM1_phi=ARM1_step['dir_dec'].values[0]
        ARM1_theta=ARM1_step['dir_inc'].values[0]
    #
    TRM2_step=data[ (data.XRM.str.contains('TRM2')==True)].head(1)
    if (len(TRM2_step)>0):
        TRM2_phi=TRM2_step['dir_dec'].values[0]
        TRM2_theta=TRM2_step['dir_inc'].values[0]
    #
    ARM2_step=data[ (data.XRM.str.contains('ARM2')==True)].head(1)
    if (len(ARM2_step)>0):
        ARM2_phi=ARM2_step['dir_dec'].values[0]
        ARM2_theta=ARM2_step['dir_inc'].values[0]
    #
    # add in method codes
    # NRM LTD demag
    data.loc[(data.XRM.str.contains('NRM0')==True),'method_codes']=\
                'LT-NO:LP-DIR-AF:'+methstring
    data.loc[((data['step']==0) &(data.XRM=='NRM')),'method_codes']=\
                'LT-LT-Z:LP-DIR-AF:'+methstring
    data.loc[((data['step']!=0) &(data.XRM=='NRM')),'method_codes']=\
                'LT-AF-Z:LP-DIR-AF:LT-AF-Z-TUMB:'+methstring
    # ARM0 LTD DEMAG
    data.loc[(data.XRM.str.contains('ARM00')==True),'method_codes']=\
                'LT-AF-I:LT-NRM-PAR:LP-ARM-AFD:'+methstring
    data.loc[((data['step']==0) &(data.XRM=='ARM0')),'method_codes']=\
                'LT-AF-I:LT-NRM-PAR:LT-LT-Z:LP-ARM-AFD:'+methstring
    data.loc[((data['step']!=0) &(data.XRM=='ARM0')),'method_codes']=\
                'LT-AF-Z:LP-ARM-AFD:LT-AF-Z-TUMB:'+methstring
    # TRM1 LTD DEMAG   
    data.loc[(data.XRM.str.contains('TRM10')==True),'method_codes']=\
                'LT-T-I:LP-TRM-AFD:'+methstring
    data.loc[((data['step']==0) &(data.XRM=='TRM1')),'method_codes']=\
                'LT-LT-Z:LP-TRM-AFD:'+methstring
    data.loc[((data['step']!=0) &(data.XRM=='TRM1')),'method_codes']=\
                'LT-AF-Z:LP-TRM-AFD:LT-AF-Z-TUMB:'+methstring
    # ARM1 LTD DEMAG
    data.loc[(data.XRM.str.contains('ARM10')==True),'method_codes']=\
                'LT-AF-I:LT-TRM-PAR:LP-ARM-AFD:'+methstring
    data.loc[((data['step']==0) &(data.XRM=='ARM1')),'method_codes']=\
                'LT-AF-I:LT-TRM-PAR:LT-LT-Z:LP-ARM-AFD:'+methstring
    data.loc[((data['step']!=0) &(data.XRM=='ARM1')),'method_codes']=\
                'LT-AF-Z:LP-ARM-AFD:LT-AF-Z-TUMB:'+methstring
    # TRM2 LTD DEMAG   
    data.loc[(data.XRM.str.contains('TRM20')==True),'method_codes']=\
                'LT-T-I:LP-TRM-AFD:'+methstring
    data.loc[((data['step']==0) &(data.XRM=='TRM2')),'method_codes']=\
                'LT-LT-Z:LP-TRM-AFD:'+methstring
    data.loc[((data['step']!=0) &(data.XRM=='TRM2')),'method_codes']=\
                'LT-AF-Z:LP-TRM-AFD:LT-AF-Z-TUMB:'+methstring
    # ARM2 LTD DEMAG
    data.loc[(data.XRM.str.contains('ARM20')==True),'method_codes']=\
                'LT-AF-I:LT-TRM-PAR:LP-ARM-AFD:'+methstring
    data.loc[((data['step']==0) &(data.XRM=='ARM2')),'method_codes']=\
                'LT-AF-I:LT-TRM-PAR:LT-LT-Z:LP-ARM-AFD:'+methstring
    data.loc[((data['step']!=0) &(data.XRM=='ARM2')),'method_codes']=\
                'LT-AF-Z:LP-ARM-AFD:LT-AF-Z-TUMB:'+methstring
    #
    data['experiment'],experiment=specimen+':'+methstring,specimen+':'+methstring
    #
    # reset lab field directions to TRM direction  for TRM steps
    data.loc[(data.method_codes.str.contains('LT-T-I')==True),'treat_dc_field']=lab_field
    if (len(TRM1_step)>0):
        data.loc[( (data.method_codes.str.contains('LT-T-I')==True)&\
                 (data.description.str.contains('TRM1'))),'treat_dc_field_phi']=TRM1_phi
        data.loc[((data.method_codes.str.contains('LT-T-I')==True)&\
                 (data.description.str.contains('TRM1'))),'treat_dc_field_theta']=TRM1_theta
    if (len(TRM2_step)>0):
        data.loc[( (data.method_codes.str.contains('LT-T-I')==True)&\
                 (data.description.str.contains('TRM2'))),'treat_dc_field_phi']=TRM2_phi
        data.loc[((data.method_codes.str.contains('LT-T-I')==True)&\
                 (data.description.str.contains('TRM2'))),'treat_dc_field_theta']=TRM2_theta
    #
    # reset lab field directions to ARM direction  for ARM steps  
    data.loc[(data.method_codes.str.contains('LT-AF-I')==True),'treat_dc_field']=ARM_DC_field
    if (len(ARM0_step)>0):
        data.loc[( (data.method_codes.str.contains('LT-AF-I')==True)&\
                 (data.description.str.contains('ARM0'))),'treat_dc_field_phi']=ARM0_phi
        data.loc[((data.method_codes.str.contains('LT-AF-I')==True)&\
                 (data.description.str.contains('ARM0'))),'treat_dc_field_theta']=ARM0_theta
    #
    if (len(ARM1_step)>0):
        data.loc[( (data.method_codes.str.contains('LT-AF-I')==True)&\
                (data.description.str.contains('ARM1'))),'treat_dc_field_phi']=ARM1_phi
        data.loc[((data.method_codes.str.contains('LT-AF-I')==True)&\
                 (data.description.str.contains('ARM1'))),'treat_dc_field_theta']=ARM1_theta
    #
    if (len(ARM2_step)>0):
        data.loc[( (data.method_codes.str.contains('LT-AF-I')==True)&\
                (data.description.str.contains('ARM2'))),'treat_dc_field_phi']=ARM2_phi
        data.loc[((data.method_codes.str.contains('LT-AF-I')==True)&\
                 (data.description.str.contains('ARM2'))),'treat_dc_field_theta']=ARM2_theta
    #
    # temperature of liquid nitrogen
    data.loc[(data.method_codes.str.contains('LT-LT-Z')==True),'treat_temp']=77
    #
    meas_data=data[['specimen','magn_mass','dir_dec','dir_inc','treat_temp','treat_ac_field',\
                   'treat_dc_field','treat_dc_field_phi','treat_dc_field_theta','meas_temp',\
                   'citations','number','experiment','method_codes','software_packages',\
                    'instrument_codes','standard','quality','description']]
    meas_data['magn_moment']=meas_data['magn_mass']*weight 
    #
    meas_data['sequence']=meas_data.index
    spec_data=pd.DataFrame([{'specimen':specimen,'sample':sample,'weight':weight,\
                'azimuth':0,'dip':0,'experiments':experiment,'result_quality':'g',\
                'method_codes':methstring,'citations':citations,'software_packages':version}])
    #
    spec_data['result_type']='i'
    spec_data['result_quality']='g'
    spec_data['description']=" "
    if azimuth==0 and dip==0:
        spec_data['dir_tilt_correction']=-1
    else:
        spec_data['dir_tilt_correction']=0
    samp_data=spec_data[['sample']]
    samp_data['site']=site
    samp_data['azimuth']=0
    samp_data['dip']=0
    samp_data['orientation_quality']='g'
    samp_data['description']=\
            'measurements directions corrected with: azimuth='+str(azimuth)+' dip='+str(dip)
    #
    # write out the data file
    return meas_data, spec_data, samp_data



def find_best_API_portion_r(combinedRegs1,minFrac,minR,minSlopeT,maxSlopeT):
    """
    Finds the best portion for NRM-TRM1* and TRM1-TRM2* plots by r criteria of Yamamoto+2003
    (1) calculate API statistics for all possible coercivity intervals
    (2) discard the statistics not satisfying the usual selection criteria (when applicable)
    omitted - (3) sort the statistics by dAPI (rel. departure from the expected API), 
                    and select the best 10 statistics
    (4) sort the statistics by frac_n, and select the best one
    Curvature (k) calculation is made by the code for Arai plot by Lisa. 
        This is done for inverterd-X (e.g. -TRM1, -ARM1, ..) and original-Y (e.g. NRM, ARM0, ..).
        The inverted-X is offset (positive) to zero as a minimum.
    revised 2021/09/06
    __________
        combinedRegs1 : combined API parameters
        minFrac,minR,minSlopeT,maxSlopeT : thresholds for the r criteria
    Returns
    ______
        trm1_star_min
        trm1_star_max
        trm2_star_min
        trm2_star_max
    """
    print('[criteria, 2nd heating]')
    #
    screened=combinedRegs1[combinedRegs1.frac_t>=minFrac]
    if (len(screened)>0):
        print('  Frac_t >=', minFrac, ': ', len(screened),'step-combinations')
    else:
        print('  Frac_t >=', minFrac, ': no step-combinations satisfied')
        screened=combinedRegs1
    #
    screened2=screened[screened.r_t>=minR]
    if (len(screened2)>0): 
        print('  r_t >=', minR, ': ', len(screened2),'step-combinations')
        screened=screened2
    else:
        print('  r_t >=', minR, ': no step-combinations satisfied')
    #
    screened3=screened[(screened.slope_t>=minSlopeT)\
                           &(screened.slope_t<=maxSlopeT)]
    if (len(screened3)>0):
        print(' ', minSlopeT, '<= slope_t <=', maxSlopeT, \
              ': ', len(screened3),'step-combinations')
        screened=screened3
    else:
        print(' ', minSlopeT, '<= slope_t <=', maxSlopeT, \
              ': no step-combinations satisfied')
    #
    print('[criteria, 1st heating]')
    #
    screened4=screened[screened.frac_n>=minFrac]
    if (len(screened4)>0):
        print('  Frac_n >=', minFrac, ': ', len(screened4),'step-combinations')
        screened=screened4
    else:
        print('  Frac_n >=', minFrac, ': no step-combinations satisfied')
    #
    screened5=screened[screened.r_n>=minR]
    if (len(screened5)>0):
        print('  r_n >=', minR, ': ', len(screened5),'step-combinations')
        screened=screened5
    else:
        print('  r_n >=', minR, ': no step-combinations satisfied')
    ## sort by dAPI, then select top 10
    #print('[sort by dAPI and select the top 10 data]')
    #screened=screened.sort_values('dAPI')
    #screened=screened.iloc[:10]
    #
    # sort by frac_n, then select the best
    print('[sort by frac_n and select the best step-combination]')
    screened=screened.sort_values('frac_n', ascending=False)
    screened_best_fn=screened.iloc[:1]
    #print(screened)
    trm2_star_min=screened_best_fn['step_min_t'].iloc[0]
    trm2_star_max=screened_best_fn['step_max'].iloc[0]
    trm1_star_min=screened_best_fn['step_min_n'].iloc[0]
    trm1_star_max=screened_best_fn['step_max'].iloc[0]
    #
    return trm1_star_min, trm1_star_max, trm2_star_min, trm2_star_max, screened



def find_best_API_portion_k(combinedRegs1,maxBeta,maxFresid,maxKrv):
    """
    Finds the best portion for NRM-TRM1* and TRM1-TRM2* plots by k' criteria of Lloyd+2021 
    (1) calculate API statistics for all possible coercivity intervals
    (2) discard the statistics not satisfying the Beta criterion (0.1) and the k' criterion (0.2)
    omitted - (3) sort the statistics by dAPI (rel. departure from the expected API), 
                and select the best 10 statistics
    (4) sort the statistics by frac_n, and select the best one
    __________
        combinedRegs1 : combined API parameters
        minFrac,minR,minSlopeT,maxSlopeT : thresholds for the r criteria
    Returns
    ______
        trm1_star_min
        trm1_star_max
        trm2_star_min
        trm2_star_max
    """
    print('[criteria, 2nd heating]')
    screened=combinedRegs1
    #
    #screened=combinedRegs1[combinedRegs1.frac_t>=minFrac]
    #if (len(screened)>0):
    #    print('  Frac_t >=', minFrac, ': ', len(screened),'step-combinations')
    #else:
    #    print('  Frac_t >=', minFrac, ': no step-combinations satisfied')
    #    screened=combinedRegs1
    ##
    #screened2=screened[screened.krvd_t<=maxKrv]
    #if (len(screened2)>0): 
    #    print('  k\' <=', maxKrv, ': ', len(screened2),'step-combinations')
    #    screened=screened2
    #else:
    #    print('  k\' <=', maxKrv, ': no step-combinations satisfied')
    ##
    #screened3=screened[(screened.slope_t>=minSlopeT)\
    #                       &(screened.slope_t<=maxSlopeT)]
    #if (len(screened3)>0):
    #    print(' ', minSlopeT, '<= slope_t <=', maxSlopeT, \
    #         ': ', len(screened3),'step-combinations')
    #    screened=screened3
    #else:
    #    print(' ', minSlopeT, '<= slope_t <=', maxSlopeT, \
    #          ': no step-combinations satisfied')
    ##
    print('[criteria, 1st heating]')
    #
    #screened4=screened[screened.frac_n>=minFrac]
    #if (len(screened4)>0):
    #    print('  Frac_n >=', minFrac, ': ', len(screened4),'step-combinations')
    #    screened=screened4
    #else:
    #    print('  Frac_n >=', minFrac, ': no step-combinations satisfied')
    #
    screened5=screened[screened.beta_n<=maxBeta]
    if (len(screened5)>0):
        print('  beta <=', maxBeta, ': ', len(screened5),'step-combinations')
        screened=screened5
    else:
        print('  beta <=', maxBeta, ': no step-combinations satisfied')
    #
    screened6=screened[screened.f_resid_n<=maxFresid]
    if (len(screened6)>0):
        print('  f_resid <=', maxBeta, ': ', len(screened6),'step-combinations')
        screened=screened6
    else:
        print('  f_resid <=', maxBeta, ': no step-combinations satisfied')
    #
    screened7=screened[abs(screened.krvd_n)<=maxKrv]
    if (len(screened7)>0):
        print('  abs_k\' <=', maxKrv, ': ', len(screened7),'step-combinations')
        screened=screened7
    else:
        print('  abs_k\' <=', maxKrv, ': no step-combinations satisfied')
    ## sort by dAPI, then select top 10
    #print('[sort by dAPI and select the top 10 data]')
    #screened=screened.sort_values('dAPI')
    #screened=screened.iloc[:10]
    # sort by frac_n, then select the best
    print('[sort by frac_n and select the best step-combination]')
    screened=screened.sort_values('frac_n', ascending=False)
    screened_fn=screened.iloc[:1]
    #print(screened)
    trm2_star_min=screened_fn['step_min_t'].iloc[0]
    trm2_star_max=screened_fn['step_max'].iloc[0]
    trm1_star_min=screened_fn['step_min_n'].iloc[0]
    trm1_star_max=screened_fn['step_max'].iloc[0]
    #
    return trm1_star_min, trm1_star_max, trm2_star_min, trm2_star_max, screened



def find_mdf(df):
    """
    Finds the median destructive field for AF demag data
    Parameters
    __________
        df : dataframe of measurements
    Returns
    ______
        mdf : median destructive field
    """
    mdf_df=df[df.meas_norm<=0.5]
    mdf_high=mdf_df.treat_ac_field_mT.values[0]
    mdf_df=df[df.meas_norm>=0.5]
    mdf_low=mdf_df.treat_ac_field_mT.values[-1]
    mdf=int(0.5*(mdf_high+mdf_low))
    return mdf



def ltd_pars(df1,afxrm,step_min,step_max,xkey,ykey):
    #
    used1=df1[(df1.treat>=step_min)&(df1.treat<=step_max)]
    n=len(used1)
    slope, b, r, p, stderr =\
        linregress(used1[xkey].values.astype('float'),\
                    used1[ykey].values.astype('float'))
    coeffs1=np.polyfit(used1[xkey].values.astype('float'),used1[ykey].values.astype('float'),1)
    coeffs2=np.polyfit(used1[xkey].values.astype('float'),used1[ykey].values.astype('float'),2)
    #
    beta=stderr/abs(slope)
    #
    krv=lib_k.AraiCurvature(x=df1[xkey],y=df1[ykey])[0]
    krv_dash=lib_k.AraiCurvature(x=used1[xkey].values.astype('float'),\
                                 y=used1[ykey].values.astype('float'))[0]
    #
    linY=np.polyval(coeffs1,used1[xkey].values.astype('float'))
    curveY=np.polyval(coeffs2,used1[xkey].values.astype('float'))
    chi1, chi2 = (used1[ykey]-linY)**2, (used1[ykey]-curveY)**2
    chi1sum, chi2sum = chi1.sum(), chi2.sum()
    dAIC = n * (np.log(chi1sum) - np.log(chi2sum)) - 2
    #
    used2=afxrm[(afxrm.treat_ac_field_mT>=step_min)&(afxrm.treat_ac_field_mT<=step_max)]
    tblock=used2[['dir_dec','dir_inc','meas_norm']]
    tall=afxrm[['dir_dec','dir_inc','meas_norm']]
    XYZ, XYZall = pmag.dir2cart(tblock).transpose(), pmag.dir2cart(tall).transpose()
    Rused, Rall = vds(XYZ), vds(XYZall)
    frac=Rused/Rall
    #
    y_int = coeffs1[1]
    y_prime = []
    for i in range(0, len(used1[ykey])):
        y_prime.append(0.5 * (used1[ykey].values.astype('float')[i] \
                                  + slope * used1[xkey].values.astype('float')[i] + y_int))
    #print(y_prime)
    delta_y_prime = abs(max(y_prime) - min(y_prime))
    f_resid = abs(y_int) / delta_y_prime
    #print('f_resid=',f_resid)
    #
    return n,slope,b,r,stderr,coeffs1,coeffs2,dAIC,frac,beta,krv,krv_dash,f_resid,used1


def ltd_pars_mod(df1,afxrm,step_min,step_max,xkey,ykey):
    #
    n, slope, b, r, stderr, coeffs1, coeffs2, dAIC, frac, beta, krv, krv_dash, f_resid, used1 =\
        ltd_pars(df1,afxrm,step_min,step_max,xkey,ykey)
    #
    return n,slope,r,dAIC,frac,step_min,step_max,beta,krv,krv_dash,f_resid



def opt_interval_first_heating(zijd_min, sid_df, afnrm, minN, minFrac, minR):
    #
    ntrmRegs1=[]
    trm1_star_min=zijd_min
    used_df=sid_df[sid_df.treat>=trm1_star_min]
    used_df=used_df[['treat','nrm','trm1_star']]
    trm1_star_max=used_df['treat'].tolist()[len(used_df)-1]
    variables = []
    for i in range(len(used_df)-minN+1):
        for j in range(len(used_df)-minN+1-i):
            variables = variables + \
                        [[used_df, afnrm, used_df['treat'].tolist()[i],\
                            used_df['treat'].tolist()[i+j+minN-1],'trm1_star','nrm']]
    p=Pool(multi.cpu_count())
    ntrmRegs1=pd.DataFrame(p.map(wrapper_ltd_pars_mod, variables))
    ntrmRegs1.columns=['n_n','slope_n','r_n','dAIC_n','frac_n',\
                       'step_min','step_max','beta_n','krv_n','krvd_n','f_resid_n']
    p.close()
    p.terminate()
    #print(ntrmRegs1)
    screened=ntrmRegs1
    screened2=ntrmRegs1[ntrmRegs1.frac_n>=minFrac]
    if (len(screened2)>0): screened=screened2
    screened3=screened[ntrmRegs1.r_n>=minR]
    if (len(screened3)>0): screened=screened3
    screened=screened.sort_values('dAIC_n')
    screened=screened.iloc[:10]
    #print(screened)
    # decide optimum interval
    trm1_star_min = screened.loc[screened.frac_n.idxmax(), "step_min"]
    trm1_star_max = screened.loc[screened.frac_n.idxmax(), "step_max"]
    print('opt interval NRM-TRM1*: %5.1f'%(trm1_star_min) \
              + ' - %5.1f'%(trm1_star_max) + ' mT')
    #
    return trm1_star_min, trm1_star_max



def opt_interval_second_heating(sid_df, aftrm1, minN, minFrac, minR, minSlopeT, maxSlopeT):
    #
    trmRegs1=[]
    # interval serach from ZERO up to MAX
    trm2_star_min=sid_df['treat'].tolist()[0]
    used_df=sid_df[sid_df.treat>=trm2_star_min]
    used_df=used_df[['treat','trm1','trm2_star']]
    trm2_star_max=used_df['treat'].tolist()[len(used_df)-1]
    variables = []
    for i in range(len(used_df)-minN+1):
        for j in range(len(used_df)-minN+1-i):
            variables = variables + [[used_df, aftrm1,\
                                        used_df['treat'].tolist()[i],\
                                        used_df['treat'].tolist()[i+j+minN-1],'trm2_star','trm1']]
    p=Pool(multi.cpu_count())
    trmRegs1=pd.DataFrame(p.map(wrapper_ltd_pars_mod, variables))
    trmRegs1.columns=['n_t','slope_t','r_t','dAIC_t','frac_t',\
                      'step_min','step_max','beta_t','krv_t','krvd_t','f_resid_t']
    p.close()
    p.terminate()
    #print(trmRegs1)
    screened=trmRegs1[trmRegs1.frac_t>=minFrac]
    screened2=screened[trmRegs1.r_t>=minR]
    if (len(screened2)>0): screened=screened2
    screened3=screened[(trmRegs1.slope_t>=minSlopeT)&(trmRegs1.slope_t<=maxSlopeT)]
    if (len(screened3)>0): screened=screened3
    screened=screened.sort_values('dAIC_t')
    screened=screened.iloc[:10]
    #print(screened)
    # decide optimum interval
    trm2_star_min = screened.loc[screened.frac_t.idxmax(), "step_min"]
    trm2_star_max = screened.loc[screened.frac_t.idxmax(), "step_max"]
    print('opt interval TRM1-TRM2*: %5.1f'%(trm2_star_min) \
              + ' - %5.1f'%(trm2_star_max) + ' mT')
    #
    return trm2_star_min, trm2_star_max



def opt_interval_zij(afnrm, minN):
    #
    # optimum interval serach from ZERO up to MAX
    variables = []
    for i in range(len(afnrm)-minN+1):
        for j in range(len(afnrm)-minN+1-i):
            variables = variables + [[afnrm,\
                                        afnrm['treat_ac_field_mT'].tolist()[i],\
                                        afnrm['treat_ac_field_mT'].tolist()[i+j+minN-1]]]
    p=Pool(multi.cpu_count())
    zijPCArsts1=pd.DataFrame(p.map(wrapper_zijd_PCA_calc, variables))
    zijPCArsts1.columns=['step_min','step_max','mad','dang','spec_n']
    zijPCArsts1['mad+dang']=zijPCArsts1['mad']+zijPCArsts1['dang']
    p.close()
    p.terminate()
    #print(zijPCArsts1)
    screened=zijPCArsts1.sort_values('mad+dang')
    screened=screened.iloc[:10]
    #print(screened)
    # decide optimum interval
    step_min_mad_min = screened.loc[screened['mad'].idxmin(), "step_min"]
    step_max_mad_min = screened.loc[screened['mad'].idxmin(), "step_max"]
    step_min_dang_min = screened.loc[screened['dang'].idxmin(), "step_min"]
    step_max_dang_min = screened.loc[screened['dang'].idxmin(), "step_max"]
    step_min_opt_zij = step_min_mad_min \
        if step_min_mad_min < step_min_dang_min else step_min_dang_min
    step_max_opt_zij = step_max_mad_min \
        if step_max_mad_min > step_max_dang_min else step_max_dang_min
    print('opt interval Zijderveld: %5.1f'%(step_min_opt_zij)+ ' - %5.1f'%(step_max_opt_zij) + ' mT')
    #
    return step_min_opt_zij, step_max_opt_zij



def plot_af_xrm(sid,sdf,ax,df,rem_type):
    #
    df=df.reset_index()
    #
    if 'ARM' in rem_type:
        xrm0=df.magn_mass_diff.tolist()[0]
        df0=sdf[sdf.description.str.contains(rem_type+'0')]
        df0=df0.tail(1)
        df0['meas_norm']=df0['magn_mass_diff']/xrm0
        dflt=df0[df0.method_codes.str.contains('LT-LT-Z')==True]
    else:
        xrm0=df.magn_mass.tolist()[0]
        df0=sdf[sdf.description.str.contains(rem_type+'0')]
        df0=df0.tail(1)
        df0['meas_norm']=df0['magn_mass']/xrm0
        dflt=df[df.method_codes.str.contains('LT-LT-Z')==True]
    #print(df0)
    #print(dflt)
    #df0=df0.reset_index()
    #dflt=dflt.reset_index()
    #
    afdmax=df['treat_ac_field_mT'].max()
    mdf=find_mdf(df)
    #
    # plot definitions
    ax.set_title(sid+'\n '+str(rem_type)+'$_0$='+'%8.2e'%(xrm0)\
              +' Am$^2$/kg ; MDF ~ '+str(mdf)+' mT')
    ax.set_xlabel('alternating field (mT)')
    ax.set_ylabel(str(rem_type)+'/'+str(rem_type)+'$_0$')
    ax.set_xlim(-10,200)
    ymax=df.meas_norm.max()
    if df0['meas_norm'].max() > 1.0:
        ax.set_ylim(-0.05,df0['meas_norm'].max()*1.1)
    else:
        ax.set_ylim(-0.05,ymax*1.1)
    # dotted line for each 0.5 interavl for Y
    for i in range(int(ymax//0.5)+1):
        ax.axhline(0.5*i,linestyle='dotted')
    #
    # plot main data
    ax.plot(df['treat_ac_field_mT'],df['meas_norm'],'ro')
    ax.plot(df['treat_ac_field_mT'],df['meas_norm'],'r-')
    # put on the last AF step magnetization
    ax.text(df['treat_ac_field_mT'].values[-1]+.05,\
             df['meas_norm'].values[-1]+.02,'%5.3f'%(df['meas_norm'].values[-1]))

    # plot the data at af=0
    if (len(df0)>0):
        ax.plot(df0['treat_ac_field_mT'],df0['meas_norm'],'wo',markeredgecolor='black')
        ax.text(df0['treat_ac_field_mT']+.075,df0['meas_norm']+.02,\
                     '%5.3f'%(df0['meas_norm']))
    if (len(dflt)>0):
        ax.plot(dflt['treat_ac_field_mT'],dflt['meas_norm'],'bo')
    #
    # normalized rations at af=0 and afmax
    ratio_0 = 0
    if (len(df0)>0):
        ratio_0 = df0['meas_norm'].values[0]
    #
    ratio_afmax = 0
    if (len(df)>0):
        ratio_afmax = df['meas_norm'].values[-1]
    #
    return afdmax, mdf, xrm0*1e6, ratio_0, ratio_afmax



def plot_ntrm_arm(sid,ax,df,afxrm,step_min,step_max,xkey,ykey):
    #
    fac=1e6
    unit=' $\mu$Am$^2$/kg'
    #
    #fac=1e3
    #unit=' mAm$^2$/kg'
    #
    n,slope,b,r,stderr,coeffs1,coeffs2,dAIC,frac,beta,krv,krv_dash,f_resid,selected_df =\
        ltd_pars(df,afxrm,step_min,step_max,xkey,ykey)
    #
    xymax=1.1*fac*np.array([[df[ykey].max(),df[xkey].max()]]).max()
    tick=[float('{:.1e}'.format(xymax*(i+1)/4)) for i in range(4)]
    if (slope<1.5): [xl, yl1, yl2, yl3, yl4]=[0.10, 0.90, 0.85, 0.80, 0.75]
    if (slope>=1.5): [xl, yl1, yl2, yl3, yl4]=[0.50, 0.20, 0.15, 0.10, 0.05]
    #
    linY=np.polyval(coeffs1,selected_df[xkey].values.astype('float'))
    #
    ax.set_title(sid)
    ax.set_xlabel(xkey.upper()+unit)
    ax.set_ylabel(ykey.upper()+unit)
    ax.set_xlim(0,xymax)
    ax.set_ylim(0,xymax)
    ax.set_xticks(tick)
    ax.set_yticks(tick)
    #
    ax.plot(df[xkey]*fac,df[ykey]*fac,'wo',markeredgecolor='black')
    ax.plot(selected_df[xkey]*fac,selected_df[ykey]*fac,'ko')
    ax.plot(fac*selected_df[xkey].values.astype('float'),fac*linY,'r-')

    ax.text(xl, yl1,'slope= %5.3f'%(slope)+'$\pm$%5.3f'%(stderr),\
            horizontalalignment='left', verticalalignment='center',\
            transform = ax.transAxes)
    ax.text(xl, yl2,'r= %5.3f'%(r)+', N = '+str(n),\
            horizontalalignment='left', verticalalignment='center',\
            transform = ax.transAxes)
    ax.text(xl, yl3,'k\'= %5.3f'%(krv_dash)+' (k= %5.3f'%(krv)+')',\
            horizontalalignment='left', verticalalignment='center',\
            transform = ax.transAxes)
    ax.text(xl, yl4,'('+str(int(step_min))+'-'+str(int(step_max))+' mT)',\
            horizontalalignment='left', verticalalignment='center',\
            transform = ax.transAxes)
    #
    return slope,r,n,krv,krv_dash



def plot_pint_main(sid,ax,df1,afxrm,xkey,ykey,step_min,step_max,aftrm1,aftrm2,spec_prv_df,criteria,minR,minFrac,minSlopeT,maxSlopeT,maxBeta,maxFresid,maxKrv,lab_field):
    #
    tick_div=4
    #
    fac=1e6
    unit=' $\mu$Am$^2$/kg'
    #
    #fac=1e3
    #unit=' mAm$^2$/kg'
    #
    n,slope,b,r,stderr,coeffs1,coeffs2,dAIC,frac,beta,krv,krv_dash,f_resid,selected_df =\
        ltd_pars(df1,afxrm,step_min,step_max,xkey,ykey)
    #
    xymax=1.1*fac*np.array([[df1[xkey].max(),df1[ykey].max()]]).max()
    tick=[float('{:.1e}'.format(xymax*(i+1)/tick_div)) for i in range(tick_div)]
    if (slope<1.5): [xl, yl1, yl2, yl3, yl4, yl5, yl6]=[0.10, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65]
    if (slope>=1.5): [xl, yl1, yl2, yl3, yl4, yl5, yl6]=[0.50, 0.35, 0.30, 0.25, 0.20, 0.15, 0.10]
    #
    linY=np.polyval(coeffs1,selected_df[xkey].values.astype('float'))
    #
    pint='rejected'
    if (xkey=='trm1_star') & (ykey=='nrm'):
        if (len(aftrm1)>0) & (len(aftrm2)>0):
            slope_t=float(spec_prv_df.loc[sid,'slope_TRM1-TRM2*'])
            if ('reg' in criteria) & (r>=minR) & (frac>=minFrac) \
                                    & (slope_t>=minSlopeT) & (slope_t<=maxSlopeT):
                pint='%7.2f'%(slope*lab_field*1e6)+' $\mu$T'
            if ('krv' in criteria) & (beta<=maxBeta) & (f_resid<=maxFresid) & (krv_dash<=maxKrv):
                pint='%7.2f'%(slope*lab_field*1e6)+' $\mu$T'
    
    ax.set_title(sid)
    #if (xkey=='trm1_star') & (ykey=='nrm'):
    #    ax.set_title(sid+' (B$_{anc}$=%7.2f'%(slope*lab_field*1e6)+' $\mu$T)')
    #else: ax.set_title(sid)
    ax.set_xlim(0,xymax)
    ax.set_ylim(0,xymax)
    ax.set_xticks(tick)
    ax.set_yticks(tick)
    if (xkey=='trm1_star') & (ykey=='nrm'):
        ax.set_xlabel('TRM1*'+unit)
        ax.set_ylabel('NRM'+unit)
    if (xkey=='trm2_star') & (ykey=='trm1'):
        ax.set_xlabel('TRM2*'+unit)
        ax.set_ylabel('TRM1'+unit)
        ax.plot([0,xymax],[0,xymax],color='g',linestyle='dotted')
    #
    ax.plot(df1[xkey]*fac, df1[ykey]*fac, 'wo', markeredgecolor='black')
    ax.plot(selected_df[xkey]*fac, selected_df[ykey]*fac, 'ko')
    ax.plot(fac*selected_df[xkey].values.astype('float'),fac*linY,'r-')
    #
    ax.text(xl, yl1,'slope= %5.3f'%(slope)+'$\pm$%5.3f'%(stderr),\
            horizontalalignment='left', verticalalignment='center', transform = ax.transAxes)
    #ax.text(xl, yl2,'r= %5.3f'%(r)+', k\'= %5.3f'%(krv_dash)+', N = '+str(n),\
    ax.text(xl, yl2,'r= %5.3f'%(r)+', N= '+str(n),\
            horizontalalignment='left', verticalalignment='center', transform = ax.transAxes)
    ax.text(xl, yl3,'FRAC= '+'%5.3f'%(frac)+', $\Delta$AIC= '+'%5.1f'%(dAIC),\
            horizontalalignment='left', verticalalignment='center', transform = ax.transAxes)
    #ax.text(xl, yl4,'$\Delta$AIC = '+'%5.1f'%(dAIC),\
    ax.text(xl, yl4,'k\'= %5.3f'%(krv_dash)+' (k= %5.3f'%(krv)+')',\
            horizontalalignment='left', verticalalignment='center', transform = ax.transAxes)
    if (xkey=='trm1_star') & (ykey=='nrm'):
        ax.text(xl, yl5,'B$_{anc}$= '+pint,\
                horizontalalignment='left', verticalalignment='center', transform = ax.transAxes)
    ax.text(xl, yl6,'('+str(int(step_min))+'-'+str(int(step_max))+' mT)',\
            horizontalalignment='left', verticalalignment='center', transform = ax.transAxes)
    #
    return slope,r,n,frac,dAIC,krv,krv_dash,f_resid,pint



def plot_xrm_xrm2_r2(sid,ax,df,afxrm,xkey,ykey,step_min,step_max):
    #
    fac=1e6
    unit=' $\mu$Am$^2$/kg'
    #
    #fac=1e3
    #unit=' mAm$^2$/kg'
    #
    n,slope,b,r,stderr,coeffs1,coeffs2,dAIC,frac,beta,krv,krv_dash,f_resid,selected_df =\
        ltd_pars(df,afxrm,step_min,step_max,xkey,ykey)
   
    if 'trm1' in xkey:
        xymax=1.1*fac*np.array([[df['trm1'].max(),df['nrm'].max()]]).max()
    if 'trm2' in xkey:
        xymax=1.1*fac*np.array([[df['trm1'].max(),df['trm2'].max(),df['nrm'].max()]]).max()
    if 'arm1' in xkey:
        xymax=1.1*fac*np.array([[df['arm0'].max(),df['arm1'].max()]]).max()
    if 'arm2' in xkey:
        xymax=1.1*fac*np.array([[df['arm0'].max(),df['arm1'].max(),df['arm2'].max()]]).max()
    tick=[float('{:.1e}'.format(xymax*(i+1)/4)) for i in range(4)]
    if (slope<1.5): [xl, yl1, yl2, yl3, yl4]=[0.10, 0.90, 0.85, 0.80, 0.75]
    if (slope>=1.5): [xl, yl1, yl2, yl3, yl4]=[0.50, 0.20, 0.15, 0.10, 0.05]
    
    ax.set_title(sid)
    ax.set_xlabel(xkey.upper()+unit)
    ax.set_ylabel(ykey.upper()+unit)
    ax.set_xlim(0,xymax)
    ax.set_ylim(0,xymax)
    ax.set_xticks(tick)
    ax.set_yticks(tick)
    #
    if ykey!='nrm':
        ax.plot([0,xymax],[0,xymax],color='g',linestyle='dotted')
    ax.plot(df[xkey]*fac,df[ykey]*fac,'wo',markeredgecolor='black')
    ax.plot(selected_df[xkey]*fac,selected_df[ykey]*fac,'ko')
    #
    ax.text(xl, yl1,'slope= %5.3f'%(slope)+'$\pm$%5.3f'%(stderr),\
            horizontalalignment='left', verticalalignment='center',\
            transform = ax.transAxes)
    ax.text(xl, yl2,'r= %5.3f'%(r)+', N = '+str(n),\
            horizontalalignment='left', verticalalignment='center',\
            transform = ax.transAxes)
    ax.text(xl, yl3,'k\'= %5.3f'%(krv_dash)+' (k= %5.3f'%(krv)+')',\
            horizontalalignment='left', verticalalignment='center',\
            transform = ax.transAxes)
    ax.text(xl, yl4,'('+str(int(step_min))+'-'+str(int(step_max))+' mT)',\
            horizontalalignment='left', verticalalignment='center',\
            transform = ax.transAxes)
    #
    return slope,r,n,krv,krv_dash



def plot_zijd(sid, sid_data, ax1, ax2, df, step_min, step_max):
    #
    # ax1 for equal-size, ax2 for close-up
    #
    whole=df
    used=df[(df.treat_ac_field_mT>=step_min)&(df.treat_ac_field_mT<=step_max)]

    xrm0=df.magn_mass.tolist()[0]
    df0=sid_data[sid_data.description.str.contains('NRM0')]
    if (len(df0.index)>0):
        df0['meas_norm']=df0['magn_mass']/xrm0
        pre_LTD=df0
    #
    ## PCA calculation
    pca_block=used[['treat_ac_field_mT','dir_dec','dir_inc','meas_norm']]
    pca_block['quality']='g'
    pca_block=pca_block[['treat_ac_field_mT','dir_dec','dir_inc','meas_norm','quality']].values.tolist()
    pca_result=pmag.domean(pca_block, 0, len(pca_block)-1, 'DE-BFL')
    #print(pca_result)
    pca_dec=pca_result['specimen_dec']
    pca_inc=pca_result['specimen_inc']
    pca_mad=pca_result['specimen_mad']
    pca_n=pca_result['specimen_n']
    #
    # title, label
    interval='('+str(int(step_min))+'-'+str(int(step_max))+' mT)'
    ax1.set_title(sid+' '+interval)
    ax2.set_title(sid+' '+interval)
    PCA='PCA: Dec= %7.1f'%(pca_dec)+', Inc= %7.1f'%(pca_inc)+', MAD= %8.2f'%(pca_mad)+', N= %2d'%(pca_n)
    ax1.set_xlabel(PCA)
    ax2.set_xlabel(PCA)
    #
    ## plot pre-LTD interval
    if len(list(df0.index))>0:
        xrm0=pre_LTD[['dir_dec','dir_inc','meas_norm']].values
        xyz_0=pmag.dir2cart(xrm0).transpose()
        ax1.plot(xyz_0[0],-xyz_0[1],color='grey',marker='o')
        ax1.plot(xyz_0[0],-xyz_0[2],color='grey',marker='s')
        ax2.plot(xyz_0[0],-xyz_0[1],color='grey',marker='o')
        ax2.plot(xyz_0[0],-xyz_0[2],color='grey',marker='s')
    #
    ## plot whole interval
    if len(list(whole.index))>0:
        zblock=whole[['dir_dec','dir_inc','meas_norm']]
        xyz_wl=pmag.dir2cart(zblock).transpose()
        ax1.plot(xyz_wl[0],-xyz_wl[1],color='grey',marker='o')
        ax1.plot(xyz_wl[0],-xyz_wl[2],color='grey',marker='s')
        ax2.plot(xyz_wl[0],-xyz_wl[1],color='grey',marker='o')
        ax2.plot(xyz_wl[0],-xyz_wl[2],color='grey',marker='s')
    #
    ## plot used interval
    zblock=used[['dir_dec','dir_inc','meas_norm']]
    XYZ=pmag.dir2cart(zblock).transpose()
    ax1.plot(XYZ[0],-XYZ[1],'ko')
    ax1.plot(XYZ[0],-XYZ[2],'ws',markeredgecolor='blue')
    ax1.plot(XYZ[0],-XYZ[1],'k-')
    ax1.plot(XYZ[0],-XYZ[2],'k-')
    ax2.plot(XYZ[0],-XYZ[1],'ko')
    ax2.plot(XYZ[0],-XYZ[2],'ws',markeredgecolor='blue')
    ax2.plot(XYZ[0],-XYZ[1],'k-')
    ax2.plot(XYZ[0],-XYZ[2],'k-')
    #
    # put on best fit line
    Rstart=np.sqrt((XYZ[0][0])**2+(XYZ[1][0])**2+(XYZ[2][0])**2)
    Rstop=np.sqrt((XYZ[0][-1])**2+(XYZ[1][-1])**2+(XYZ[2][-1])**2)
    XYZ_start=pmag.dir2cart([pca_dec,pca_inc,Rstart])
    XYZ_stop=-1*pmag.dir2cart([pca_dec,pca_inc,Rstop])
    ax1.plot([XYZ_start[0],XYZ_stop[0]],[-XYZ_start[1],-XYZ_stop[1]],'r-')
    ax1.plot([XYZ_start[0],XYZ_stop[0]],[-XYZ_start[2],-XYZ_stop[2]],'r-')
    ax2.plot([XYZ_start[0],XYZ_stop[0]],[-XYZ_start[1],-XYZ_stop[1]],'r-')
    ax2.plot([XYZ_start[0],XYZ_stop[0]],[-XYZ_start[2],-XYZ_stop[2]],'r-')
    #
    # get max and min
    [xmax,xmin,ymax,ymin]=[0,0,0,0]
    if len(list(df0.index))>0:
        xmax=np.max([xyz_0[0].max(),xyz_wl[0].max()])
        xmin=np.min([xyz_0[0].min(),xyz_wl[0].min()])
        ymax=np.max([(-xyz_0[1]).max(),(-xyz_0[2]).max(),\
                     (-xyz_wl[1]).max(),(-xyz_wl[2]).max()])
        ymin=np.min([(-xyz_0[1]).min(),(-xyz_0[2]).min(),\
                     (-xyz_wl[1]).min(),(-xyz_wl[2]).min()])
    else:
        xmax=np.max([xyz_wl[0].max()])
        xmin=np.min([xyz_wl[0].min()])
        ymax=np.max([(-xyz_wl[1]).max(),(-xyz_wl[2]).max()])
        ymin=np.min([(-xyz_wl[1]).min(),(-xyz_wl[2]).min()])
    #print(xmin, xmax)
    #print(ymin, ymax)
    [xlength, ylength]=[xmax-xmin, ymax-ymin]
    xylength=max(xlength, ylength)
    #
    # plot size adjustment for ax1
    div=2
    tick1=[float('{:.1e}'.format(-xylength*(i+1)/div)) for i in range(div)]
    tick2=[0.0]
    tick3=[float('{:.1e}'.format(xylength*(i+1)/div)) for i in range(div)]
    tick=tick1 + tick2 + tick3
    ax1.plot([-xylength*1.1, xylength*1.1],[0,0],'k-')
    ax1.set_xlim(-xylength*1.1, xylength*1.1)
    ax1.plot([0,0], [-xylength*1.1, xylength*1.1],'k-')
    ax1.set_ylim(-xylength*1.1, xylength*1.1)
    ax1.set_xticks(tick)
    ax1.set_yticks(tick)
    #
    # plot size adjustment for ax2
    if xmin>0:
        ax2.plot([-xlength*0.1, xmax+xlength*0.1],[0,0],'k-')
        ax2.set_xlim(-xlength*0.1, xmax+xlength*0.1)
    if xmin<0:
        if xmax<0:
            ax2.plot([xmin-xlength*0.1, xlength*0.1],[0,0],'k-')
            ax2.set_xlim(xmin-xlength*0.1, xlength*0.1)
        if xmax>0:
            ax2.plot([xmin-xlength*0.1, xmax+xlength*0.1],[0,0],'k-')
            ax2.set_xlim(xmin-xlength*0.1, xmax+xlength*0.1)
    if ymin>0:
        ax2.plot([0,0], [-ylength*0.1, ymax+ylength*0.1],'k-')
        ax2.set_ylim(-ylength*0.1, ymax+ylength*0.1)
    if ymin<0:
        if ymax<0:
            ax2.plot([0,0], [ymin-ylength*0.1, ylength*0.1],'k-')
            ax2.set_ylim(ymin-ylength*0.1, ylength*0.1)
        if ymax>0:
            ax2.plot([0,0], [ymin-ylength*0.1, ymax+ylength*0.1],'k-')
            ax2.set_ylim(ymin-ylength*0.1, ymax+ylength*0.1)
    #
    return pca_dec, pca_inc, pca_mad, pca_n



def prep_sid_df(xrm_types, df):
    # subtract the last treatment step from the others for all types
    # set afxrm data for all types (afnrm, afarm0, ...)
    for t in xrm_types:
        if t=='NRM':  afnrm, sd_diff_n =set_NTRM_data(df,t)
        if t=='TRM1': aftrm1,sd_diff_t1=set_NTRM_data(df,t)
        if t=='TRM2': aftrm2,sd_diff_t2=set_NTRM_data(df,t)
        if t=='ARM0': afarm0,sd_diff_a0=set_ARM_data(df,t)
        if t=='ARM1': afarm1,sd_diff_a1=set_ARM_data(df,t)
        if t=='ARM2': afarm2,sd_diff_a2=set_ARM_data(df,t)
    print ('NRM: ',len(afnrm),' data, TRM1:',len(aftrm1),' data, TRM2:',len(aftrm2),' data')
    print ('ARM0: ',len(afarm0),' data, ARM1:',len(afarm1),' data, ARM2:',len(afarm2),' data')
    # set data for bi-plot: merged by the treatment steps against each other
    if (len(afnrm)>0):
        sid0_df=afnrm[['treat_ac_field_mT','magn_mass_diff']]
        sid0_df.columns=['treat','nrm']
        sid_df=sid0_df
        sid_data_diff=sd_diff_n
    if (len(afarm0)>0):
        sid0_df=afarm0[['treat_ac_field_mT','magn_mass_diff']]
        sid0_df.columns=['treat','arm0']
        sid_df=sid_df[['treat','nrm']].merge(\
                sid0_df[['treat','arm0']], on='treat')
        sid_data_diff=pd.concat([sid_data_diff,sd_diff_a0])
    if (len(aftrm1)>0):
        sid0_df=aftrm1[['treat_ac_field_mT','magn_mass_diff']]
        sid0_df.columns=['treat','trm1']
        sid_df=sid_df[['treat','nrm','arm0']].merge(\
                sid0_df[['treat','trm1']], on='treat')
        sid_data_diff=pd.concat([sid_data_diff,sd_diff_t1])
    if (len(afarm1)>0):
        sid0_df=afarm1[['treat_ac_field_mT','magn_mass_diff']]
        sid0_df.columns=['treat','arm1']
        sid_df=sid_df[['treat','nrm','arm0','trm1']].merge(\
                sid0_df[['treat','arm1']], on='treat')
        sid_data_diff=pd.concat([sid_data_diff,sd_diff_a1])
    if (len(aftrm2)>0):
        sid0_df=aftrm2[['treat_ac_field_mT','magn_mass_diff']]
        sid0_df.columns=['treat','trm2']
        sid_df=sid_df[['treat','nrm','arm0','trm1','arm1']].merge(\
                sid0_df[['treat','trm2']], on='treat')
        sid_data_diff=pd.concat([sid_data_diff,sd_diff_t2])
    if (len(afarm2)>0):
        sid0_df=afarm2[['treat_ac_field_mT','magn_mass_diff']]
        sid0_df.columns=['treat','arm2']
        sid_df=sid_df[['treat','nrm','arm0','trm1','arm1','trm2']].merge(\
                sid0_df[['treat','arm2']], on='treat')
        sid_data_diff=pd.concat([sid_data_diff,sd_diff_a2])
    last_treat=sid_df.treat.max()
    # need to peel off the last step for division step
    sid_df=sid_df[sid_df.treat<last_treat]
    # calculate TRM1* and TRM2*
    if (len(aftrm1)>0) & (len(afarm0)>0) & (len(afarm1)>0):
        sid_df['trm1_star']=sid_df['trm1']*(sid_df['arm0']/sid_df['arm1'])
    if (len(aftrm2)>0) & (len(afarm1)>0) & (len(afarm2)>0):
        sid_df['trm2_star']=sid_df['trm2']*(sid_df['arm1']/sid_df['arm2'])   
    # put the last treatment step back in (as zero)
    last_df=pd.DataFrame([np.zeros(len(list(sid_df.columns)))])
    last_df.columns=sid_df.columns
    last_df['treat']=last_treat
    new_df=pd.concat((sid_df,last_df))
    new_df.reset_index(inplace=True,drop=True)
    sid_df=new_df
    #
    return sid_data_diff,sid_df,afnrm,aftrm1,aftrm2,afarm0,afarm1,afarm2



def set_ARM_data(df,rem_type):
    """ choose and calculate ARM data (except pre-LTD 0 data) from the inpud data
    Paramters
    _________
        df : dataframe of measurement data
        rem_type : remanence type
    Returns
    ________
        afxrm : XRM data with "meas_norm" column
        df3   : with base-vector-subtracted data
    """
    XRM0 = str(rem_type) + '0'
    df2=subtract_base_vector(df,rem_type)
    df3=df2[df2.description.str.contains(rem_type)]
    afxrm=df3
    if (len(afxrm)>0):
        meas0=afxrm.magn_mass_diff.tolist()[0]
        afxrm['meas_norm']=afxrm['magn_mass_diff']/meas0
        afxrm=afxrm.loc[afxrm.method_codes.str.contains('LT-LT-Z')==False]
        afxrm=df2[df2.description.str.contains(rem_type)]
        afxrm=afxrm[afxrm.description.str.contains(XRM0)==False]
        meas0=afxrm.magn_mass_diff.tolist()[0]
        afxrm['meas_norm']=afxrm['magn_mass_diff']/meas0
    return afxrm,df3



def set_NTRM_data(df,rem_type):
    """ choose and calculate NTRM data from the inpud data
    Paramters
    _________
        df : dataframe of measurement data
        rem_type : remanence type
    Returns
    ________
        afxrm : XRM data with "meas_norm" column
        df3   : with base-vector-subtracted data
    """
    XRM0 = str(rem_type) + '0'
    df2=subtract_base_vector(df,rem_type)
    df3=df2[df2.description==rem_type]
    df4=df2[df2.description.str.contains(XRM0)==True]
    df5=pd.concat([df3,df4])
    #df5.to_csv('_temp.csv',index=True)
    afxrm=df3
    if (len(afxrm)>0):
        afxrm=afxrm[afxrm.description.str.contains(XRM0)==False]
        meas0=afxrm.magn_mass.tolist()[0] # get first measurement (after LTD)
        afxrm['meas_norm']=afxrm['magn_mass']/meas0 # normalized by first measurement
    return afxrm,df5



def vds(xyz):
    R=0
    cart=xyz.transpose()
    for i in range(xyz.shape[1]-1):
        diff=[cart[i][0]-cart[i+1][0],cart[i][1]-cart[i+1][1],cart[i][2]-cart[i+1][2]]
        dirdiff=pmag.cart2dir(diff)
        R+=dirdiff[2]
    return R



def wrapper_ltd_pars_mod(args):
    return ltd_pars_mod(*args)



def wrapper_zijd_PCA_calc(args):
    return zijd_PCA_calc(*args)



def zijd_PCA_calc(df,start,end):
    #
    used=df[(df.treat_ac_field_mT>=start)&(df.treat_ac_field_mT<=end)]
    pca_block=used[['treat_ac_field_mT','dir_dec','dir_inc','meas_norm']]
    pca_block['quality']='g'
    pca_block=pca_block[['treat_ac_field_mT','dir_dec','dir_inc','meas_norm','quality']].values.tolist()
    pca_result=pmag.domean(pca_block, 0, len(pca_block)-1, 'DE-BFL')
    mad=pca_result['specimen_mad']
    dang=pca_result['specimen_dang']
    spec_n=pca_result['specimen_n']
    step_min=pca_result['measurement_step_min']
    step_max=pca_result['measurement_step_max']
    #print('%5.1f'%(step_min) + ' - %5.1f'%(step_max) + ' mT : MAD= %5.2f'%(mad) \
    #        + ', DANG= %5.2f'%(dang) + ', N= %2d'%(spec_n)) 
    #
    return step_min,step_max,mad,dang,spec_n 



