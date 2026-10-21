"""Exercise actual supervisor/driver processes with synthetic GCS mode and IMU."""
def check(run, state, auto, commands, statuses, lifecycle, modes):
    def await_drive():
        import time
        deadline=time.monotonic()+8
        while (not commands or commands[-1][1]<.19 or not statuses
               or abs(statuses[-1]['heading']['target_rad']-1.2)>1e-5) and time.monotonic()<deadline:
            run(.1)
    state["heading"]=None
    run(1)
    assert lifecycle and not lifecycle[-1]['running'] and not commands
    assert not lifecycle[-1]['sensors_running'] and not lifecycle[-1]['terrain_running']
    state['brain']=False;auto[0]=True
    run(.5)
    assert lifecycle[-1]['waiting_heading'] and not lifecycle[-1]['running']
    assert lifecycle[-1]['sensors_running'] and lifecycle[-1]['terrain_running']
    state['heading']=.4
    run(3)
    assert lifecycle[-1]['running']
    assert not any(v or w for _,v,w in commands), 'movement before brain ready'
    assert abs(statuses[-1]['heading']['target_rad']-.4)<1e-5
    state['brain']=True;run(2)
    assert commands[-1][1]>.19
    state['heading']=.8;run(.7)
    assert commands[-1][1]>.19 and commands[-1][2]<-.3
    assert abs(statuses[-1]['heading']['target_rad']-.4)<1e-5
    state['hazard']='wall';run(.7)
    assert commands[-1][1]==0 and abs(commands[-1][2])>=.3
    assert abs(statuses[-1]['heading']['target_rad']-.4)<1e-5
    state['hazard']='none';state['heading']=.4;run(1.5)
    assert commands[-1][1]>.19 and abs(commands[-1][2])<.01
    auto[0]=False;run(1)
    assert not lifecycle[-1]['running'] and commands[-1][1:]==(0.,0.)
    assert not lifecycle[-1]['sensors_running'] and not lifecycle[-1]['terrain_running']
    assert not modes, 'external driver must not take cFS mode socket'
    state['heading']=1.2;run(.3);auto[0]=True;run(2);await_drive()
    assert lifecycle[-1]['running'] and commands[-1][1]>.19, (lifecycle[-1], commands[-1], statuses[-1])
    assert abs(statuses[-1]['heading']['target_rad']-1.2)<1e-5
    auto[0]=False;run(.1);auto[0]=True;run(2);await_drive()
    assert lifecycle[-1]['running'] and commands[-1][1]>.19, (lifecycle[-1], commands[-1], statuses[-1])
    auto[0]=False;run(1)
    assert not lifecycle[-1]['running']
    assert not lifecycle[-1]['sensors_running'] and not lifecycle[-1]['terrain_running']
    auto[0]=True;run(2)
    assert lifecycle[-1]['sensors_running']
    state['age']=2.;run(2)
    assert not lifecycle[-1]['running']
    assert not lifecycle[-1]['sensors_running'] and not lifecycle[-1]['terrain_running']
    auto[0]=False;state['age']=0.;run(.3)

if __name__=='__main__':
    from drive_ros import main
    main(gcs=True)
