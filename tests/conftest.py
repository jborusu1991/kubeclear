import os

os.environ.setdefault('KUBECONFIG', os.path.join(os.path.dirname(__file__), 'dummy_kubeconfig.yaml'))
os.environ.setdefault('NUMBER_OF_NODES_UPGRADE', '1')
