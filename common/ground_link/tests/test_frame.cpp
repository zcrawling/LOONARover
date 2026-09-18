#include "loonar/ground_link/frame.hpp"
#include <bit>
#include <cassert>
#include <cstring>
#include <limits>
namespace gl=loonar::ground_link;
int main(){
  const gl::ManualCommand manual{0.4,1.0};const auto payload=gl::encode_manual(manual);const gl::Frame source{gl::Type::kManualCommand,42,payload};const auto encoded=gl::encode(source);const auto decoded=gl::decode(encoded);assert(decoded&&decoded->sequence==42&&decoded->type==gl::Type::kManualCommand);const auto motion=gl::decode_manual(decoded->payload);assert(motion&&motion->linear_mps==0.4&&motion->angular_radps==1.0);
  const gl::ActivityCommand activity{7,3,{1,2,3}};const auto activity_roundtrip=gl::decode_activity(gl::encode_activity(activity));assert(activity_roundtrip&&activity_roundtrip->request_id==7&&activity_roundtrip->opcode==3&&activity_roundtrip->parameters==activity.parameters);
  gl::StreamDecoder stream;assert(stream.append(std::span<const std::uint8_t>(encoded.data(),5)));assert(!stream.next());assert(stream.append(std::span<const std::uint8_t>(encoded.data()+5,encoded.size()-5)));assert(stream.next());
  auto bad_magic=encoded;bad_magic[0]=0;assert(!gl::decode(bad_magic));auto bad_length=encoded;bad_length[12]=0xff;bad_length[13]=0xff;assert(!gl::decode(bad_length));
  gl::Frame oversized{gl::Type::kEvent,1,std::vector<std::uint8_t>(gl::kMaxPayloadSize+1)};assert(gl::encode(oversized).empty());
  const std::vector<std::uint8_t> command_result{42,0,0,0,2,0,1,1,2,0};
  const auto result=gl::decode_command_result(command_result);assert(result&&result->ground_sequence==42&&result->command_type==2&&result->cfs_received&&result->adapter_forwarded&&result->current_mode==2&&result->result_code==0);
  std::vector<std::uint8_t> gateway(20);gateway[0]=3;gateway[1]=1;gateway[2]=1;const double linear=0.4,angular=1.0;const auto linear_bits=std::bit_cast<std::uint64_t>(linear),angular_bits=std::bit_cast<std::uint64_t>(angular);for(unsigned i=0;i<8;++i){gateway[4+i]=static_cast<std::uint8_t>(linear_bits>>(8*i));gateway[12+i]=static_cast<std::uint8_t>(angular_bits>>(8*i));}const auto gateway_status=gl::decode_gateway_status(gateway);assert(gateway_status&&gateway_status->mode==3&&gateway_status->last_linear_mps==0.4&&gateway_status->last_angular_radps==1.0);
  std::vector<std::uint8_t> vehicle(92);vehicle[0]=0xd2;vehicle[1]=0x04;vehicle[8]=1;const auto voltage_bits=std::bit_cast<std::uint64_t>(11.7);for(unsigned i=0;i<8;++i)vehicle[12+i]=static_cast<std::uint8_t>(voltage_bits>>(8*i));const auto vehicle_status=gl::decode_vehicle_status(vehicle);assert(vehicle_status&&vehicle_status->timestamp_ms==1234&&vehicle_status->valid_flags==1&&vehicle_status->battery_voltage==11.7);vehicle.pop_back();assert(!gl::decode_vehicle_status(vehicle));
  std::vector<std::uint8_t> mcu(50);mcu[0]=1;mcu[8]=2;const auto temperature_bits=std::bit_cast<std::uint64_t>(42.5);for(unsigned i=0;i<8;++i)mcu[16+i]=static_cast<std::uint8_t>(temperature_bits>>(8*i));const auto mcu_status=gl::decode_mcu_status(mcu);assert(mcu_status&&mcu_status->timestamp_ms==1&&mcu_status->uptime_ms==2&&mcu_status->board_temperature_c==42.5);mcu.pop_back();assert(!gl::decode_mcu_status(mcu));
  std::vector<std::uint8_t> devices(9+7*9);devices[8]=7;const auto device_status=gl::decode_device_status(devices);assert(device_status&&device_status->devices.size()==7);devices.pop_back();assert(!gl::decode_device_status(devices));
  std::vector<std::uint8_t> event(16+3+4);event[8]=2;event[13]=3;event[14]=4;std::memcpy(event.data()+16,"cfsboom",7);const auto decoded_event=gl::decode_event(event);assert(decoded_event&&decoded_event->severity==2&&decoded_event->source=="cfs"&&decoded_event->text=="boom");
  return 0;
}
