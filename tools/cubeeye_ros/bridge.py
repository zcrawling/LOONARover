"""CubeEye SDK XYZ -> ROS2 PointCloud2. Host callback timestamps, metres."""
import argparse,json,os,signal,struct,subprocess,threading,time
from pathlib import Path
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2,PointField
from std_msgs.msg import String
from geometry_msgs.msg import TransformStamped
from tf2_ros import StaticTransformBroadcaster
from scipy.spatial.transform import Rotation


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,default=Path.home()/'cubeeye_sdk')
    p.add_argument('--helper',type=Path,help='Use a prebuilt native helper instead of compiling at startup')
    p.add_argument('--seconds',type=float,default=0);p.add_argument('--hz',type=float,default=5.)
    p.add_argument('--stride',type=int,default=4);p.add_argument('--output',type=Path)
    p.add_argument('--no-base-tf',action='store_true',help='Publish in cubeeye_optical only; mounting geometry is not measured yet')
    p.add_argument('--reliable',action='store_true',help='Use reliable ROS delivery for local bag recording')
    for key,val in [('x',.15),('y',0.),('z',.033),('roll',0.),('pitch',0.),('yaw',0.)]:p.add_argument('--'+key,type=float,default=val)
    a=p.parse_args()
    if a.hz<=0 or a.stride<1:p.error('positive hz/stride required')
    sdk=a.sdk
    libdirs=[sdk/'lib',sdk/'thirdparty/liblive555/lib/Release',*[d for d in (sdk/'thirdparty').glob('*/lib') if d.parent.name!='python']]
    env=os.environ.copy();env['LD_LIBRARY_PATH']=':'.join(map(str,libdirs))
    if a.helper:
        binary=a.helper.resolve()
        if not binary.is_file() or not os.access(binary,os.X_OK):
            p.error('--helper must name an executable native helper')
    else:
        build=Path.home()/'.cache/loonar/cubeeye';build.mkdir(parents=True,exist_ok=True)
        binary=build/'capture_xyz';src=Path(__file__).with_name('capture_xyz.cpp')
        subprocess.run(['g++','-std=c++17','-O2','-pthread',str(src),'-I'+str(sdk/'include/CubeEye'),'-L'+str(sdk/'lib'),'-lCubeEye',*['-Wl,-rpath-link,'+str(d) for d in libdirs],'-o',str(binary)],env=env,check=True)
    rclpy.init();node=Node('cubeeye_i200dk')
    cloud_qos=rclpy.qos.QoSProfile(depth=10) if a.reliable else rclpy.qos.qos_profile_sensor_data
    pub=node.create_publisher(PointCloud2,'/tof/depth/points',cloud_qos);diag=node.create_publisher(String,'/tof/status',10)
    if not a.no_base_tf:
        broadcaster=StaticTransformBroadcaster(node);tf=TransformStamped();tf.header.stamp=node.get_clock().now().to_msg();tf.header.frame_id='base_link';tf.child_frame_id='cubeeye_optical'
        tf.transform.translation.x=a.x;tf.transform.translation.y=a.y;tf.transform.translation.z=a.z
        optical=np.array([[0,0,1],[-1,0,0],[0,-1,0]])
        q=Rotation.from_matrix(Rotation.from_euler('xyz',[a.roll,a.pitch,a.yaw]).as_matrix()@optical).as_quat()
        tf.transform.rotation.x,tf.transform.rotation.y,tf.transform.rotation.z,tf.transform.rotation.w=map(float,q);broadcaster.sendTransform(tf)
    readfd,writefd=os.pipe();latest=[];lock=threading.Lock();errors=[]
    def receive():
        def read_n(f,n):
            data=bytearray()
            while len(data)<n:
                chunk=f.read(n-len(data))
                if not chunk:raise EOFError('SDK stream closed')
                data.extend(chunk)
            return data
        try:
            with os.fdopen(readfd,'rb',buffering=0) as f:
                while True:
                    magic,w,h,stamp,device=struct.unpack('<IIIQQ',read_n(f,28))
                    if magic!=0x58595A31 or not 0<w*h<=1000000:raise ValueError('invalid frame header')
                    xyz=np.frombuffer(read_n(f,w*h*12),dtype='<f4').reshape(3,h,w)[:,::a.stride,::a.stride].reshape(3,-1).T.copy()
                    with lock:latest[:]=[stamp,device,xyz,w,h]
        except Exception as exc:errors.append(str(exc))
    thread=threading.Thread(target=receive,daemon=True);thread.start()
    child=subprocess.Popen([str(binary),str(writefd)],pass_fds=[writefd],env=env);os.close(writefd)
    begin=time.monotonic();last=0;count=0
    if a.output:a.output.mkdir(parents=True,exist_ok=True)
    try:
        while rclpy.ok() and (not a.seconds or time.monotonic()-begin<a.seconds):
            tick=time.monotonic()
            if errors:raise RuntimeError(errors[-1])
            with lock:sample=latest.copy()
            if sample and sample[0]!=last:
                last,device,xyz,w,h=sample;valid=np.isfinite(xyz).all(axis=1)&(xyz[:,2]>.1)&(np.linalg.norm(xyz,axis=1)<5.)
                pts=np.ascontiguousarray(xyz[valid],dtype='<f4')
                m=PointCloud2();m.header.frame_id='cubeeye_optical';m.header.stamp.sec=int(last//1000000000);m.header.stamp.nanosec=int(last%1000000000)
                m.height=1;m.width=len(pts);m.fields=[PointField(name=n,offset=i*4,datatype=PointField.FLOAT32,count=1) for i,n in enumerate('xyz')];m.is_bigendian=False;m.point_step=12;m.row_step=12*len(pts);m.is_dense=True;m.data=pts.tobytes();pub.publish(m);count+=1
                status=dict(frames=count,width=w,height=h,valid_points=len(pts),z_median=float(np.median(pts[:,2])) if len(pts) else None,host_callback_ns=last,device_timestamp=device,units='SDK XYZ metres',timestamp='host SDK callback, not exposure',fps=count/(time.monotonic()-begin))
                d=String();d.data=json.dumps(status);diag.publish(d)
                if count%5==1:print(json.dumps(status),flush=True)
                if a.output and count<=30:np.save(a.output/f'cloud_{count:04d}.npy',pts)
                if a.output:(a.output/'status.json').write_text(json.dumps(status,indent=2))
            elif not sample and time.monotonic()-begin>20:raise RuntimeError('No XYZ frame received')
            rclpy.spin_once(node,timeout_sec=0);time.sleep(max(0,1/a.hz-(time.monotonic()-tick)))
    except KeyboardInterrupt:pass
    finally:
        child.send_signal(signal.SIGINT)
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait()
        node.destroy_node()
        if rclpy.ok():rclpy.shutdown()

if __name__=='__main__':main()
