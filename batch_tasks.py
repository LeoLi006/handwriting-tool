"""Sequential independent jobs; the caller owns UI dispatch and cancellation."""
import warnings

import handwriting as hw


def run_batch(jobs, params, cancel, notify, converter=None):
    if converter is None:
        from managed_output import generate_document
        converter = generate_document
    results = []
    for job in jobs:
        path = job['path']
        if cancel():
            result = dict(job, status='已取消', paths=[], notices=[], error='')
        else:
            notify('job', dict(job, status='转换中', paths=[], error=''))
            try:
                with warnings.catch_warnings(record=True) as notes:
                    warnings.simplefilter('always', UserWarning)
                    paths = converter(path, cancel=cancel,
                                      page_progress=lambda n: notify('page', (job['id'], n)), **params)
                result = dict(job, status='完成', paths=paths,
                              notices=list(dict.fromkeys(str(n.message) for n in notes)), error='')
            except hw.ConversionCancelled:
                result = dict(job, status='已取消', paths=[], notices=[], error='')
            except (Exception, SystemExit) as exc:
                result = dict(job, status='失败', paths=[], notices=[], error=str(exc))
        results.append(result)
        notify('job', result)
    return results
