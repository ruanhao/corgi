MASTER_IP=${master_ip}

cat >>/etc/hosts<<EOF
$MASTER_IP  master
EOF

# Join worker nodes to the Kubernetes cluster
apt-get install -y sshpass
sshpass -p "kubeadmin" scp -o StrictHostKeyChecking=no root@master:/joincluster.sh /joincluster.sh
bash /joincluster.sh
