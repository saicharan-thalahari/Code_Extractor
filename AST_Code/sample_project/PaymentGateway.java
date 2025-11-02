package com.example.pay;

import com.example.util.Helper;

public class PaymentGateway {
    public boolean charge(String id, double amount) {
        Helper.log("Charging " + id + " amount=" + amount);
        return true;
    }
}
