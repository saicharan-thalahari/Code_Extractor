package com.example.service;

import com.example.model.Transaction;
import com.example.util.Helper;

public class TransactionService {
    public void process(Transaction t) {
        Helper.log("Processing tx " + t.getId());
    }
}
