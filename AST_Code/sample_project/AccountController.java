package com.example.web;

import com.example.service.UserService;
import com.example.service.TransactionService;
import com.example.model.User;

public class AccountController {
    private UserService us = new UserService();
    private TransactionService tx = new TransactionService();

    public void createAndProcess(String userId, String name) {
        User u = new User(userId, name);
        us.register(u);
        tx.process(new com.example.model.Transaction("tx-" + userId));
    }
}
