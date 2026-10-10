"""SDK subprocess exits/hangs/reappears; real ROS adapter, no USB or motors."""
import importlib.machinery
import json
from pathlib import Path
import tempfile
import time
import rclpy
from sensor_msgs.msg import Image
from rclpy.qos import qos_profile_sensor_data


def main():
    path = Path(__file__).resolve().parents[1]/'scripts/tof_adapter'
    adapter_module = importlib.machinery.SourceFileLoader('adapter_under_test', str(path)).load_module()
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); helper=root/'fake_sdk'
        helper.write_text('''#!/usr/bin/env python3
import os,sys,time,struct
from pathlib import Path
p=Path(__file__).with_name('runs')
n=int(p.read_text())+1 if p.exists() else 1
p.write_text(str(n))
if n==1:
    sys.stderr.write('fake NoSuchDevice\\n');sys.exit(1)
for seq in range(1,1000):
    stamp=time.time_ns()
    head=struct.pack('<4IQ12d',0x4C544F46,8,8,seq,stamp,10.,10.,3.5,3.5,*([0.]*8))
    os.write(int(sys.argv[1]),head+struct.pack('<128H',*([1000]*64+[100]*64)))
    if n==2 and seq==4:time.sleep(60)
    time.sleep(.04)
''')
        helper.chmod(0o755)
        rclpy.init(args=['--ros-args','-p','source:=sdk','-p',f'helper:={helper}',
                         '-p','source_rectified:=true'])
        node=adapter_module.Adapter()
        frames=[]
        node.create_subscription(Image,'/loonar/tof/depth',lambda m:frames.append(m.header.stamp),qos_profile_sensor_data)
        try:
            end=time.monotonic()+12
            while time.monotonic()<end:
                rclpy.spin_once(node,timeout_sec=.05)
                if node.sdk_restarts>=2 and len(frames)>=8:break
            assert node.sdk_restarts>=2, node.sdk_restarts
            assert len(frames)>=8, len(frames)
            assert int((root/'runs').read_text())==3
            child=node.child
        finally:
            node.destroy_node();rclpy.shutdown()
        assert child.poll() is not None
        print(json.dumps({'passed':True,'restart_after_exit':True,'restart_after_hang':True,'frames':len(frames),'hardware':False}))

if __name__=='__main__':main()
