import math
from types import SimpleNamespace
from loonar_fly.heading import HeadingGoal,yaw_from_quaternion


def test_heading_reference_persists_across_avoidance():
    h=HeadingGoal();h.observe(.4);h.observe(1.0)
    command={'linear_mps':.2,'angular_rps':.3}
    assert h.command(command,{'mode':'turn'})==command
    out=h.command(command,{'mode':'cruise'})
    assert out['angular_rps']<0 and h.target==.4 and out['linear_mps']==.2
    h.observe(.4)
    assert h.command({'linear_mps':.2,'angular_rps':0},{'mode':'cruise'})['angular_rps']==0


def test_heading_wrap_and_turn_back():
    h=HeadingGoal(math.pi-.05);h.observe(-math.pi+.05)
    assert abs(h.error+.1)<1e-9
    h=HeadingGoal(0);h.observe(2)
    out=h.command({'linear_mps':.2,'angular_rps':0},{'mode':'cruise'})
    assert out['linear_mps']==0 and out['angular_rps']==-.4
    assert h.target==0


def test_quaternion_yaw_and_explicit_new_session_reference():
    q=SimpleNamespace(x=0,y=0,z=math.sin(.3),w=math.cos(.3))
    assert abs(yaw_from_quaternion(q)-.6)<1e-9
    h=HeadingGoal(1.1);h.observe(.6)
    assert h.target==1.1
