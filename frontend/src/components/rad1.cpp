#include <bits/stdc++.h>
using namespace std;

int minOperations(int n, vector<int>& arr) {
    unordered_map<int, int> freq;
    for (int x : arr) {
        freq[x]++;
    }
    int maxFreq = 0;
    for (auto &p : freq) {
        maxFreq = max(maxFreq, p.second);
    }
    return n - maxFreq;
}

int main() {
    int n;
    cin >> n;

    vector<int> arr(n);
    for (int i = 0; i < n; i++) {
        cin >> arr[i];
    }

    cout << minOperations(n, arr) << endl;

    return 0;
}