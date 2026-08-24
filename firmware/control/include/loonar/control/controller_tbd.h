#ifndef LOONAR_CONTROL_CONTROLLER_TBD_H
#define LOONAR_CONTROL_CONTROLLER_TBD_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  float left_duty;
  float right_duty;
} LnrMotorDuty;

typedef struct {
  unsigned char reserved;
} LnrControllerTbd;

void lnr_controller_tbd_init(LnrControllerTbd *controller);
LnrMotorDuty lnr_controller_tbd_step(LnrControllerTbd *controller,
                                     float linear_velocity_mps,
                                     float yaw_rate_radps);

#ifdef __cplusplus
}
#endif

#endif
