package com.example.service;

import com.example.repo.AccountRepository;
import com.example.model.User;
import com.example.util.Helper;

public class UserService {
    private AccountRepository repo = new AccountRepository();

    public void register(User u) {
        Helper.log("Registering user " + u.getName());
        repo.save(u.getId());
    }
}
