KUBERNETES_VERSION=${kubernetes_version}
KUBERNETES_VERSION=${KUBERNETES_VERSION:-1.23.6}

APT_KUBERNETES_VERSION=${KUBERNETES_VERSION}-00

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install apt-transport-https ca-certificates curl software-properties-common -y

# Adding apt repo
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
# Add kubernetes sources list into the sources.list directory
cat <<EOF | sudo tee /etc/apt/sources.list.d/kubernetes.list
deb https://apt.kubernetes.io/ kubernetes-xenial main
EOF
apt-get update -y

# Install docker container engine
apt-get install docker-ce -y

# Enable docker service
cat <<EOF >/etc/docker/daemon.json
{
  "exec-opts": ["native.cgroupdriver=systemd"],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m"
  }
}
EOF
systemctl enable docker
systemctl restart docker

# Add sysctl settings
cat >>/etc/sysctl.d/kubernetes.conf<<EOF
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
EOF
sysctl --system

# Disable swap
sed -i '/swap/d' /etc/fstab
swapoff -a

# Install Kubernetes kubeadm, kubelet and kubectl
apt-get install -y kubelet=$APT_KUBERNETES_VERSION kubeadm=$APT_KUBERNETES_VERSION kubectl=$APT_KUBERNETES_VERSION

# Start and Enable kubelet service
systemctl enable kubelet
systemctl start kubelet

# Enable ssh password authentication
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
systemctl restart sshd

# Set Root password
echo -e "kubeadmin\nkubeadmin" | passwd root
#echo "kubeadmin" | passwd --stdin root

# Preconfigure for glusterfs
modprobe dm_thin_pool # kernel module that gluster needs
echo dm_thin_pool >>/etc/modules
add-apt-repository ppa:gluster/glusterfs-8 -y
apt-get -y install glusterfs-client
# https://github.com/gluster/gluster-kubernetes/issues/510 (this is like a charm, dynamic pv will fail if without these rm)
rm -rf /var/lib/heketi
rm -rf /etc/glusterfs
rm -rf /var/lib/glusterd
rm -rf /var/lib/misc/glusterfsd
