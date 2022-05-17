POD_NETWORK=$pod_network
POD_NETWORK=${POD_NETWORK:-192.168.0.0/16}

METRICS_SERVER_VERSION=$metrics_server_version
METRICS_SERVER_VERSION=${METRICS_SERVER_VERSION:-0.6.1}

HELM_VERSION=$helm_version
HELM_VERSION=${HELM_VERSION:-3.4.2}

CNI_PLUGIN=$cni_plugin
CNI_PLUGIN=${CNI_PLUGIN:-flannel}

CROSS_SUBNET=$cross_subnet

# Initialize Kubernetes Cluster
kubeadm init --kubernetes-version=v${KUBERNETES_VERSION} \
        --apiserver-advertise-address=0.0.0.0 \
        --pod-network-cidr=$POD_NETWORK \
    | tee /tmp/kubeinit.log

# enable Swagger UI:
# 1. Add --enable-swagger-ui=true to API manifest file /etc/kubernetes/manifests/kube-apiserver.yaml
# 2. Save the file (API pod will restart itself)
# 3. See https://jonnylangefeld.com/blog/kubernetes-how-to-view-swagger-ui

# # Copy Kube admin config
mkdir -p /root/.kube
cp /etc/kubernetes/admin.conf /root/.kube/config

# Network configuration
if [[ "$CNI_PLUGIN" = flannel ]]; then
    if [[ "$CROSS_SUBNET" = True ]]; then
        curl https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml | \
            sed "s|10.244.0.0/16|$POD_NETWORK|" | kubectl apply -f -
    else
        # Deploy Flannel network (Directrouting is only suitable when all hosts locates in flat L2 network)
        curl https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml | \
            sed "s|10.244.0.0/16|$POD_NETWORK|" | sed  's/"Type": "vxlan"/"Type": "vxlan", "Directrouting": true/' | kubectl apply -f -
    fi
elif [[ "$CNI_PLUGIN" = calico ]]; then
    kubectl create -f https://projectcalico.docs.tigera.io/manifests/tigera-operator.yaml
    if [[ "$CROSS_SUBNET" = True ]]; then
        curl https://projectcalico.docs.tigera.io/manifests/custom-resources.yaml | sed 's/VXLANCrossSubnet/VXLAN/' | kubectl apply -f -
    else
        kubectl create -f https://projectcalico.docs.tigera.io/manifests/custom-resources.yaml
    fi
fi


# Deploy metrics-server (can use `kubectl top` then)
curl -L -s https://github.com/kubernetes-sigs/metrics-server/releases/download/v${METRICS_SERVER_VERSION}/components.yaml  | sed '/secure-port/ a \        - --kubelet-insecure-tls' | kubectl apply -f -

# Generate Cluster join command
kubeadm token create --print-join-command | tee /joincluster.sh

# Intalling helm
curl https://baltocdn.com/helm/signing.asc | apt-key add -
echo "deb https://baltocdn.com/helm/stable/debian/ all main" | tee /etc/apt/sources.list.d/helm-stable-debian.list
apt-get update
apt-get install helm=${HELM_VERSION}-1 -y
helm completion bash > /etc/bash_completion.d/helm

# Customize bashrc
apt-get install bash-completion -y
kubectl completion bash > /etc/bash_completion.d/kubectl
curl -o /etc/kube-ps1.sh https://raw.githubusercontent.com/jonmosco/kube-ps1/master/kube-ps1.sh
cat <<'EOF' | tee -a /root/.bashrc
alias kcd='kubectl config set-context $(kubectl config current-context) --namespace '
alias k=kubectl
complete -F __start_kubectl k
source /etc/kube-ps1.sh
export PS1='$(kube_ps1)\$ '
EOF
