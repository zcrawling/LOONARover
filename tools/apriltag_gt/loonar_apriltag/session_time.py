"""Measured laptop-to-Pi clock mapping, preserving original timestamps."""
import bisect
import csv
import json
import math
from pathlib import Path


def clock_mapping(samples, epoch):
    if not samples:
        raise ValueError('No clock measurements')
    ordered = sorted(samples, key=lambda s: s['local_epoch'])
    times = [s['local_epoch'] for s in ordered]
    i = bisect.bisect_right(times, epoch)
    left, right = ordered[max(0, i-1)], ordered[min(i, len(ordered)-1)]
    if right['local_epoch'] == left['local_epoch']:
        weight = 0.
    else:
        weight = (epoch-left['local_epoch']) / (right['local_epoch']-left['local_epoch'])
    offset = left['offset_s'] + weight*(right['offset_s']-left['offset_s'])
    return offset, max(left['rtt_s'], right['rtt_s']) / 2


def align_session(directory):
    directory = Path(directory)
    state = json.loads((directory / 'session.json').read_text())
    samples = [json.loads(line)['best'] for line in
               (directory / 'clock_samples.jsonl').read_text().splitlines() if line.strip()]
    camera = directory / 'camera'
    source = camera / 'video_frames.csv'
    if not source.exists():
        raise ValueError('No raw frame timestamp archive')
    summary = dict(frames=0, laptop_clock_steps=0, nonmonotonic_pi_timestamps=0,
                   camera_delay_s=state['camera_delay_s'], hardware_exposure_verified=False,
                   clock_model='linear interpolation between SSH minimum-RTT samples; endpoint offset outside measured range',
                   time_domain='Pi CLOCK_REALTIME; use message header/embedded stamps, not just bag receipt time',
                   uncertainty='clock_rtt_half_s describes SSH timing only, not calibrated exposure accuracy')
    previous = None
    with source.open() as src, (directory / 'timestamps.csv').open('w') as dst:
        fields = ['video_frame', 'laptop_receipt_epoch', 'receipt_monotonic_ns', 'pi_epoch',
                  'clock_offset_s', 'clock_rtt_half_s', 'seconds_since_first_frame', 'clock_step']
        writer = csv.DictWriter(dst, fieldnames=fields)
        writer.writeheader()
        first_mono = None
        for row in csv.DictReader(src):
            epoch, mono = float(row['read_completed_epoch']), int(row['receipt_monotonic_ns'])
            if not math.isfinite(epoch):
                raise ValueError('Non-finite camera timestamp')
            offset, bound = clock_mapping(samples, epoch)
            pi_epoch = epoch + offset - state['camera_delay_s']
            step = previous is not None and abs((epoch-previous[0])-(mono-previous[1])/1e9) > .02
            summary['laptop_clock_steps'] += int(step)
            summary['nonmonotonic_pi_timestamps'] += int(previous is not None and pi_epoch <= previous[2])
            if first_mono is None:
                first_mono = mono
            writer.writerow(dict(video_frame=row['frame'], laptop_receipt_epoch=f'{epoch:.9f}',
                receipt_monotonic_ns=mono, pi_epoch=f'{pi_epoch:.9f}', clock_offset_s=offset,
                clock_rtt_half_s=bound, seconds_since_first_frame=(mono-first_mono)/1e9,
                clock_step=int(step)))
            previous = epoch, mono, pi_epoch
            summary['frames'] += 1
    summary['clock_offset_span_s'] = max(s['offset_s'] for s in samples)-min(s['offset_s'] for s in samples)
    summary['timing_review_required'] = bool(summary['laptop_clock_steps'] or
        summary['nonmonotonic_pi_timestamps'] or summary['clock_offset_span_s'] > .02)
    controller = directory / 'controller.jsonl'
    if controller.exists():
        with controller.open() as src, (directory / 'controller_pi.jsonl').open('w') as dst:
            for line in src:
                event = json.loads(line)
                epoch = event['laptop_epoch_ns'] / 1e9
                offset, bound = clock_mapping(samples, epoch)
                event.update(pi_epoch=epoch+offset, clock_offset_s=offset,
                             clock_rtt_half_s=bound)
                dst.write(json.dumps(event)+'\n')
    (directory / 'timing.json').write_text(json.dumps(summary, indent=2))
    return summary
