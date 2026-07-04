from aegis.transport.sender import SmartSender, AegisHTTP, RustSenderWrapper
http = AegisHTTP('http://localhost:8000', api_token='test_token')
sender = SmartSender(http, 'run_123')
print('Sender type:', type(sender))
assert isinstance(sender, RustSenderWrapper), 'Fallback failed to use RustSenderWrapper!'
sender.start()
sender.enqueue({'step': 1, 'metrics': {'loss': 0.5}})
import time
time.sleep(2)
sender.stop()
print('Success!')
